import { diagnosticMessage } from './diagnostics';
import type { AnalysisRecording } from './types';
import type { Artifact, Detail, Kind } from './api-types';
import { bytes, duration, labels, outputNames, recording, seconds } from './api-mapping';
import { emptyChannels, loadTelemetry, imuChannels, encoderChannels } from './telemetry';
export function artifactUrl(id: number, kind: Kind, artifact: Artifact): string {
  const route = {
    thumbnail: 'thumbnail/media',
    front_preview: 'front-preview/media',
    topdown_preview: 'topdown-preview/media',
    imu_series: 'imu-series/data',
    encoder_series: 'encoder-series/data',
    ai_description: '',
  }[kind];
  if (
    !Number.isSafeInteger(artifact.id) ||
    artifact.id < 1 ||
    artifact.url !== `/api/recordings/${id}/${route}/${artifact.id}`
  )
    throw new Error('Invalid artifact identity or URL.');
  const start = seconds(artifact.coverage_start_ns),
    end = seconds(artifact.coverage_end_ns);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end < start)
    throw new Error('Invalid artifact coverage.');
  return artifact.url;
}
export const outputMessage = (state?: string) =>
  ({
    processing: 'This is currently processing.',
    queued: 'This is currently queued.',
    failed: 'This output failed.',
    not_requested: 'This output has not been prepared.',
    unavailable: 'This output is unavailable.',
  })[state ?? 'unavailable'] ?? 'This output is unavailable.';
export async function analysisRecording(
  detail: Detail,
  signal: AbortSignal,
  previous: AnalysisRecording | null,
): Promise<AnalysisRecording> {
  const row = recording(detail);
  const description = detail.outputs.find((o) => o.kind === 'ai_description');
  const aiDescription = description?.state === 'ready' ? detail.ai_description : null;
  if (
    aiDescription &&
    (typeof aiDescription.description !== 'string' ||
      !aiDescription.description.trim() ||
      aiDescription.description.length > 1000 ||
      typeof aiDescription.bunker !== 'boolean')
  )
    throw new Error('Invalid AI description.');
  const errors = [
    detail.diagnostic,
    ...detail.outputs
      .filter(
        (o) =>
          !(
            o.state === 'unavailable' &&
            [
              'imu_topic_unavailable',
              'encoder_topic_unavailable',
              'topdown_video_unavailable',
              'topdown_timestamps_unavailable',
            ].includes(o.diagnostic?.code ?? '')
          ),
      )
      .map((o) => o.diagnostic),
    ...detail.components
      .filter(
        (c) =>
          !(c.condition === 'missing' && ['topdown_video', 'topdown_timestamps'].includes(c.role)),
      )
      .map((c) => c.diagnostic),
  ]
    .filter((d) => d != null)
    .map(diagnosticMessage);
  if (detail.duration_ns === '0')
    errors.push(
      'Metadata reports zero duration. The database schema was checked, but message timestamps have not been verified.',
    );
  if (!detail.source_present) errors.push('The recording source is no longer present.');
  const bundle = {
    duration: Math.max(0, seconds(detail.duration_ns)),
    startUnix: seconds(detail.start_time_ns),
    channels: emptyChannels(),
    timestamped: true,
    absoluteTime: detail.start_time_ns !== null,
    message: '',
    mediaVersion: '',
  };
  const cameras: AnalysisRecording['cameras'] = [];
  for (const kind of ['front_preview', 'topdown_preview'] as const) {
    const output = detail.outputs.find((o) => o.kind === kind);
    const camera: AnalysisRecording['cameras'][number] = {
      id: kind === 'front_preview' ? 'front' : 'top',
      label: kind === 'front_preview' ? 'Front' : 'Top',
      region: kind === 'front_preview' ? 'Front camera view' : 'Top down camera view',
      src: '',
      alt: outputNames[kind],
      media: true,
      message: outputMessage(output?.state),
    };
    if (output?.state === 'ready' && output.artifact) {
      try {
        camera.src = artifactUrl(detail.id, kind, output.artifact);
        camera.start = seconds(output.artifact.coverage_start_ns);
        camera.end = seconds(output.artifact.coverage_end_ns);
        camera.message = '';
        if (kind === 'front_preview' && output.artifact.streams?.length) {
          camera.streams = output.artifact.streams.map((stream, index) => {
            if (stream.index !== index || stream.url !== `${camera.src}/streams/${index}`)
              throw new Error('Invalid camera stream URL.');
            const start = seconds(stream.coverage_start_ns),
              end = seconds(stream.coverage_end_ns);
            if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end < start)
              throw new Error('Invalid camera stream coverage.');
            bundle.duration = Math.max(bundle.duration, end);
            return { topic: stream.topic, src: stream.url, start, end };
          });
        }
        for (const skipped of output.artifact.skipped_streams ?? [])
          if (skipped.code !== 'front_encoding_unsupported')
            errors.push(`${skipped.topic}: ${skipped.message}`);
        bundle.duration = Math.max(bundle.duration, camera.end);
      } catch (error) {
        errors.push(String(error));
      }
    }
    cameras.push(camera);
  }
  bundle.mediaVersion = JSON.stringify(cameras.map(({ src, start, end }) => [src, start, end]));
  const telemetryOutputs = detail.outputs.filter((o) =>
    ['imu_series', 'encoder_series'].includes(o.kind),
  );
  const pendingTelemetry = telemetryOutputs.find((output) =>
    ['not_requested', 'queued', 'processing', 'failed'].includes(output.state),
  );
  bundle.message = pendingTelemetry
    ? outputMessage(pendingTelemetry.state)
    : cameras.some((camera) => camera.src)
      ? ''
      : outputMessage(telemetryOutputs.find((o) => o.state !== 'unavailable')?.state);
  for (const kind of ['imu_series', 'encoder_series'] as const) {
    const output = telemetryOutputs.find((o) => o.kind === kind);
    if (output?.state !== 'ready' || !output.artifact) continue;
    const label = kind === 'encoder_series' ? 'Encoder' : 'IMU';
    try {
      artifactUrl(detail.id, kind, output.artifact);
      const identity = `${kind}-${output.artifact.id}`;
      const names = kind === 'encoder_series' ? encoderChannels : imuChannels;
      const old =
        previous?.id === String(detail.id)
          ? previous.outputs.find((o) => o.name === outputNames[kind])
          : undefined;
      const channels =
        previous &&
        old?.identity === identity &&
        names.some((name) => previous.bundle.channels[name].available)
          ? previous.bundle.channels
          : await loadTelemetry(detail.id, output.artifact, signal, kind);
      for (const name of names) bundle.channels[name] = channels[name];
      bundle.duration = Math.max(bundle.duration, seconds(output.artifact.coverage_end_ns));
      bundle.message = '';
    } catch (error) {
      if (signal.aborted) throw error;
      bundle.message = `${label} data is unavailable.`;
      errors.push(error instanceof Error ? error.message : `${label} data could not be loaded.`);
    }
  }
  if (
    previous?.id === String(detail.id) &&
    Object.keys(bundle.channels).every(
      (name) =>
        bundle.channels[name as keyof typeof bundle.channels] ===
        previous.bundle.channels[name as keyof typeof bundle.channels],
    )
  )
    bundle.channels = previous.bundle.channels;

  return {
    id: String(detail.id),
    aiDescription,
    descriptionState: description?.state ?? 'not_requested',
    name: detail.name,
    topics: detail.topics,
    timing: detail.timing,
    healthIssues: row.healthIssues,
    bundle,
    errors: [...new Set(errors)],
    cameras,
    info: [
      { label: 'Recorded', value: '—', kind: 'time', dateTime: row.recordedAt || undefined },
      { label: 'Duration', value: duration(detail.duration_ns), kind: 'text' },
      { label: 'Source size', value: bytes(detail.total_source_size_bytes), kind: 'text' },
      { label: 'Storage', value: detail.storage_format ?? '—', kind: 'code' },
      { label: 'Messages', value: detail.message_count ?? '—', kind: 'text' },
      { label: 'Topics', value: String(detail.topic_count ?? '—'), kind: 'text' },
    ],
    outputs: detail.outputs
      .filter((output) => output.kind !== 'ai_description')
      .map((output) => ({
        name: outputNames[output.kind],
        size: bytes(output.artifact?.size_bytes),
        format:
          output.kind === 'thumbnail'
            ? 'PNG'
            : ['imu_series', 'encoder_series'].includes(output.kind)
              ? 'JSON'
              : 'MP4 · H.264',
        status: labels[output.state] ?? 'Unavailable',
        identity:
          ['imu_series', 'encoder_series'].includes(output.kind) && output.artifact
            ? `${output.kind}-${output.artifact.id}`
            : undefined,
      })),
    sources: detail.components.map((component) => ({
      name:
        {
          metadata: 'ROS metadata',
          ros_database: 'Rosbag',
          topdown_video: 'Top-down video',
          topdown_timestamps: 'Top-down timestamps',
        }[component.role] ?? component.role,
      format: component.file_name ?? '—',
      size: bytes(component.size_bytes),
      status:
        component.condition === 'readable' || component.condition === 'present'
          ? 'Readable'
          : component.condition.replace(/^./, (c) => c.toUpperCase()),
    })),
  };
}
