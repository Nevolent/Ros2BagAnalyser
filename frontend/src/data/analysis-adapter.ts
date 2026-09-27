import type { AnalysisRecording } from './types';
import type { Artifact, Detail, Kind } from './api-types';
import { bytes, duration, labels, outputNames, recording, seconds } from './api-mapping';
import { emptyChannels, loadTelemetry } from './telemetry';
export function artifactUrl(id: number, kind: Kind, artifact: Artifact): string {
  const route = {
    front_preview: 'front-preview/media',
    topdown_preview: 'topdown-preview/media',
    imu_series: 'imu-series/data',
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
  const errors = [
    detail.diagnostic,
    ...detail.outputs
      .filter(
        (o) =>
          !(
            o.state === 'unavailable' &&
            [
              'front_topic_unavailable',
              'imu_topic_unavailable',
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
    .map((d) => `${d.code}: ${d.message}`);
  if (row.health === 'Review')
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
        bundle.duration = Math.max(bundle.duration, camera.end);
      } catch (error) {
        errors.push(String(error));
      }
    }
    cameras.push(camera);
  }
  bundle.mediaVersion = JSON.stringify(cameras.map(({ src, start, end }) => [src, start, end]));
  const imu = detail.outputs.find((o) => o.kind === 'imu_series');
  bundle.message = outputMessage(imu?.state);
  if (imu?.state === 'ready' && imu.artifact) {
    try {
      artifactUrl(detail.id, 'imu_series', imu.artifact);
      const identity = `imu-${imu.artifact.id}`;
      const old =
        previous?.id === String(detail.id)
          ? previous.outputs.find((o) => o.name === outputNames.imu_series)
          : undefined;
      bundle.channels =
        previous && old?.identity === identity && !previous.bundle.message
          ? previous.bundle.channels
          : await loadTelemetry(detail.id, imu.artifact, signal);
      bundle.duration = Math.max(bundle.duration, seconds(imu.artifact.coverage_end_ns));
      bundle.message = '';
    } catch (error) {
      if (signal.aborted) throw error;
      bundle.message = 'IMU data is unavailable.';
      errors.push(error instanceof Error ? error.message : 'IMU data could not be loaded.');
    }
  }
  return {
    id: String(detail.id),
    name: detail.name,
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
      { label: 'ROS database', value: row.health, kind: 'status' },
    ],
    outputs: detail.outputs.map((output) => ({
      name: outputNames[output.kind],
      size: bytes(output.artifact?.size_bytes),
      format: output.kind === 'imu_series' ? 'JSON' : 'MP4 · H.264',
      status: labels[output.state] ?? 'Unavailable',
      identity:
        output.kind === 'imu_series' && output.artifact ? `imu-${output.artifact.id}` : undefined,
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
