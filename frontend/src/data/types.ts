/** UI domain models. API payloads can be mapped to these at the service boundary. */
export type RecordingStatus =
  'Ready' | 'Failed' | 'Not planned' | 'Queued' | 'Processing' | 'Partially prepared';
export interface Recording {
  id: string;
  name: string;
  folderId: string;
  recordedAt: string;
  duration: string;
  size: string;
  health: 'Readable' | 'Damaged' | 'Review';
  analysis: RecordingStatus;
}
export interface Folder {
  id: string;
  name: string;
  children?: Folder[];
}
export interface OutputFailure {
  output: string;
  code: string;
}
export interface Job {
  jobIds?: number[];
  recordingId?: string;
  readyIn?: number | null;
  canCancel?: boolean;
  runtimeKnown?: boolean;
  id: string;
  name: string;
  queuedAt: number;
  duration: number;
  outputs: number;
  size: string;
  completedAt?: number;
  failures?: OutputFailure[];
}
export interface ActiveJob {
  id?: number;
  recordingId?: number;
  live?: boolean;
  idle?: boolean;
  status?: string;
  estimateStatus?: 'available' | 'unavailable' | 'exceeded';
  controls?: string[];
  name: string;
  elapsed: number;
  duration: number;
  paused: boolean;
  cancelled: boolean;
}
export interface WorkspaceSnapshot {
  loading?: boolean;
  error?: string;
  busy?: boolean;
  scanning?: boolean;
  lastScan?: string | null;
  analysisLoading?: boolean;
  analysisError?: string;
  more?: Partial<Record<'queued' | 'failed' | 'history', boolean>>;
  recordings: Recording[];
  queue: Job[];
  failures: Job[];
  history: Job[];
  active: ActiveJob;
}
export type Channel = `${'angular_velocity' | 'linear_acceleration'}.${'x' | 'y' | 'z'}`;
export interface Sample {
  timeNs: bigint;
  timeSeconds: number;
  value: number | null;
}
export interface Signal {
  available?: boolean;
  samples?: Sample[];
  coverageStart?: number;
  coverageEnd?: number;
  values: number[];
  ticks: number[];
  unit: string;
  spokenUnit: string;
}
export interface AnalysisBundle {
  duration: number;
  startUnix: number;
  channels: Record<Channel, Signal>;
  timestamped?: boolean;
  absoluteTime?: boolean;
  mediaVersion?: string;
  message?: string;
}
export type MoveDirection = 'earlier' | 'later';
export interface RecordingAsset {
  identity?: string;
  name: string;
  size: string;
  format: string;
  status: string;
}
export interface AnalysisRecording {
  id?: string;
  errors?: string[];
  name: string;
  bundle: AnalysisBundle;
  info: {
    label: string;
    value: string;
    kind: 'time' | 'code' | 'status' | 'text';
    dateTime?: string;
  }[];
  outputs: RecordingAsset[];
  sources: RecordingAsset[];
  cameras: {
    id: string;
    label: string;
    region: string;
    src: string;
    alt: string;
    media?: boolean;
    start?: number;
    end?: number;
    message?: string;
  }[];
}
