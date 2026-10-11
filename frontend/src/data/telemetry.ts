import graph, { type Parsed } from './imu-graph.js';
import type { AnalysisBundle, Channel, Sample, Signal } from './types';
import type { Artifact } from './api-types';
import { request } from './http';
interface ImuMetadata {
  state: string;
  artifact: { data_url: string; size_bytes: string; series: unknown[] } | null;
}
export { graph };
export const imuChannels = [
  'angular_velocity.x',
  'angular_velocity.y',
  'angular_velocity.z',
  'linear_acceleration.x',
  'linear_acceleration.y',
  'linear_acceleration.z',
] as const;
export const encoderChannels = [
  'encoder.FL',
  'encoder.FR',
  'encoder.ML',
  'encoder.MR',
  'encoder.RL',
  'encoder.RR',
] as const;
export const channelNames = [...imuChannels, ...encoderChannels];
export const wheelLabels = {
  'encoder.FL': 'Front left (FL)',
  'encoder.FR': 'Front right (FR)',
  'encoder.ML': 'Middle left (ML)',
  'encoder.MR': 'Middle right (MR)',
  'encoder.RL': 'Rear left (RL)',
  'encoder.RR': 'Rear right (RR)',
};
export function channelLabel(channel: Channel | 'encoders') {
  return channel === 'encoders'
    ? 'Encoders · six wheels'
    : (wheelLabels[channel as keyof typeof wheelLabels] ?? channel);
}
export function emptyChannels(): Record<Channel, Signal> {
  return Object.fromEntries(
    channelNames.map((name) => [
      name,
      {
        values: [],
        samples: [],
        available: false,
        ticks: [1, 0.5, 0, -0.5, -1],
        unit: name.startsWith('encoder') ? 'RPM' : name.startsWith('angular') ? 'rad/s' : 'm/s²',
        spokenUnit: name.startsWith('encoder')
          ? 'revolutions per minute'
          : name.startsWith('angular')
            ? 'radians per second'
            : 'meters per second squared',
      },
    ]),
  ) as unknown as Record<Channel, Signal>;
}
export async function loadTelemetry(
  id: number,
  expected: Artifact,
  signal: AbortSignal,
  kind: 'imu_series' | 'encoder_series' = 'imu_series',
): Promise<AnalysisBundle['channels']> {
  const label = kind === 'encoder_series' ? 'Encoder' : 'IMU';
  const route = kind === 'encoder_series' ? 'encoder-series' : 'imu-series';
  const expectedChannels: readonly Channel[] =
    kind === 'encoder_series' ? encoderChannels : imuChannels;
  const metadata = await request<ImuMetadata>(`/api/recordings/${id}/${route}`, signal);
  if (
    metadata.state !== 'ready' ||
    !metadata.artifact ||
    metadata.artifact.data_url !== expected.url
  )
    throw new Error(`${label} artifact identity changed. Reloading recording details is required.`);
  const maximum = 256 * 1024 * 1024;
  if (Number(expected.size_bytes) > maximum || Number(metadata.artifact.size_bytes) > maximum)
    throw new Error(`${label} data exceeds the 256 MiB limit.`);
  const response = await fetch(expected.url, {
    signal: AbortSignal.any([signal, AbortSignal.timeout(60000)]),
    credentials: 'same-origin',
  });
  if (!response.ok || !response.body) throw new Error(`${label} data could not be loaded.`);
  let size = 0;
  const bounded = response.body.pipeThrough(
    new TransformStream<Uint8Array, Uint8Array>({
      transform(chunk, controller) {
        size += chunk.byteLength;
        if (size > maximum) throw new Error(`${label} data exceeds the 256 MiB limit.`);
        controller.enqueue(chunk);
      },
    }),
  );
  let parsed: Parsed;
  try {
    parsed = await graph.parseSeriesStream(bounded, metadata.artifact);
  } catch (error) {
    await bounded.cancel().catch(() => {});
    throw error;
  }
  if (
    parsed.series.length !== expectedChannels.length ||
    parsed.series.some(
      (definition, index) =>
        definition.component !== expectedChannels[index] ||
        definition.columnIndex !== index + 1 ||
        definition.units !== (kind === 'encoder_series' ? 'RPM' : index < 3 ? 'rad/s' : 'm/s²'),
    )
  )
    throw new Error(`${label} channel definitions do not match the supported wheel/axis order.`);
  const channels = emptyChannels();
  const samplesBySeries = new Map<string, Sample[]>();
  for (const definition of parsed.series) {
    if (!expectedChannels.includes(definition.component as Channel))
      throw new Error(`Unsupported ${label} channel.`);
    if (!definition.available) continue;
    const name = definition.component as Channel;
    const min = definition.minimumValue!,
      max = definition.maximumValue!;
    const padding = Math.max((max - min) * 0.1, Math.abs(max) * 0.01, 0.001);
    const low = min - padding,
      high = max + padding;
    channels[name] = {
      values: [],
      available: true,
      get samples() {
        let samples = samplesBySeries.get(definition.id);
        if (!samples) {
          samples = graph.selectSeries(parsed, definition.id).samples;
          samplesBySeries.set(definition.id, samples);
          if (samplesBySeries.size > (kind === 'encoder_series' ? 6 : 3))
            samplesBySeries.delete(samplesBySeries.keys().next().value!);
        }
        return samples;
      },
      ticks: Array.from({ length: 5 }, (_, i) => high - ((high - low) * i) / 4),
      unit: definition.units,
      spokenUnit: channels[name].spokenUnit,
      coverageStart: parsed.coverageStart,
      coverageEnd: parsed.coverageEnd,
    };
  }
  return channels;
}
