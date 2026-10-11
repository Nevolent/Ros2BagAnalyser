import type { Sample } from './types';

interface Definition {
  id: string;
  component: string;
  columnIndex: number;
  available: boolean;
  minimumValue: number | null;
  maximumValue: number | null;
  units: string;
}
export interface Parsed {
  rows: { timeNs: bigint; timeSeconds: number; values: (number | null)[] }[];
  series: Definition[];
  coverageStart: number;
  coverageEnd: number;
}
interface Graph {
  timestampGapSamples(samples: Sample[]): Sample[];
  parseSeriesStream(body: ReadableStream<Uint8Array>, artifact: unknown): Promise<Parsed>;
  selectSeries(parsed: Parsed, id: string): { samples: Sample[] };
  sampleAtOrBefore(samples: Sample[], time: number): Sample | null;
  extremeSpikeGaps(samples: Sample[]): {
    samples: Sample[];
    spikes: Sample[];
    gaps: { start: number; end: number; spikes: Sample[] }[];
  };
  visibleSpikes(spikes: Sample[], start: number, end: number, width: number): Sample[];
  visibleTraceSegments(samples: Sample[], start: number, end: number, width: number): Sample[][];
}
declare const graph: Readonly<Graph>;
export default graph;
