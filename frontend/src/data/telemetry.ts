// Reuse the production parser and spike/gap-preserving reduction without changing the old UI.
import '../../../src/rosbag_analyser/web/imu_graph.js';
import type { AnalysisBundle, Channel, Sample, Signal } from './types';
import type { Artifact } from './api-types';
import { request } from './http';
interface Definition {
  id: string;
  component: string;
  available: boolean;
  minimumValue: number | null;
  maximumValue: number | null;
  units: string;
}
interface Parsed {
  rows: { timeNs: bigint; timeSeconds: number; values: (number | null)[] }[];
  series: Definition[];
  coverageStart: number;
  coverageEnd: number;
}
interface ImuMetadata {
  state: string;
  artifact: { data_url: string; size_bytes: string; series: unknown[] } | null;
}
interface Graph {
  parseSeriesStream(body: ReadableStream<Uint8Array>, artifact: unknown): Promise<Parsed>;
  selectSeries(parsed: Parsed, id: string): { samples: Sample[] };
  sampleAtOrBefore(samples: Sample[], time: number): Sample | null;
  visibleTraceSegments(samples: Sample[], start: number, end: number, width: number): Sample[][];
}
export const graph = (window as unknown as { ImuGraph: Graph }).ImuGraph;
export const channelNames = [
  'angular_velocity.x',
  'angular_velocity.y',
  'angular_velocity.z',
  'linear_acceleration.x',
  'linear_acceleration.y',
  'linear_acceleration.z',
] as const;
export function emptyChannels(): Record<Channel, Signal> {
  return Object.fromEntries(
    channelNames.map((name) => [
      name,
      {
        values: [],
        samples: [],
        available: false,
        ticks: [1, 0.5, 0, -0.5, -1],
        unit: name.startsWith('angular') ? 'rad/s' : 'm/s²',
        spokenUnit: name.startsWith('angular') ? 'radians per second' : 'meters per second squared',
      },
    ]),
  ) as unknown as Record<Channel, Signal>;
}
export async function loadTelemetry(
  id: number,
  expected: Artifact,
  signal: AbortSignal,
): Promise<AnalysisBundle['channels']> {
  const metadata = await request<ImuMetadata>(`/api/recordings/${id}/imu-series`, signal);
  if (
    metadata.state !== 'ready' ||
    !metadata.artifact ||
    metadata.artifact.data_url !== expected.url
  )
    throw new Error('IMU artifact identity changed. Reloading recording details is required.');
  const maximum = 64 * 1024 * 1024;
  if (Number(expected.size_bytes) > maximum || Number(metadata.artifact.size_bytes) > maximum)
    throw new Error('IMU data exceeds the 64 MiB limit.');
  const response = await fetch(expected.url, { signal, credentials: 'same-origin' });
  if (!response.ok || !response.body) throw new Error('IMU data could not be loaded.');
  let size = 0;
  const bounded = response.body.pipeThrough(
    new TransformStream<Uint8Array, Uint8Array>({
      transform(chunk, controller) {
        size += chunk.byteLength;
        if (size > maximum) throw new Error('IMU data exceeds the 64 MiB limit.');
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
  const channels = emptyChannels();
  let cached: { id: string; samples: Sample[] } | null = null;
  for (const definition of parsed.series) {
    if (!channelNames.includes(definition.component as Channel))
      throw new Error('Unsupported IMU channel.');
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
        if (cached?.id !== definition.id)
          cached = {
            id: definition.id,
            samples: graph.selectSeries(parsed, definition.id).samples,
          };
        return cached.samples;
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
