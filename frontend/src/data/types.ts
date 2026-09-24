/** UI domain models. API payloads can be mapped to these at the service boundary. */
export type RecordingStatus = 'Ready' | 'Failed' | 'Not planned' | 'Queued';
export interface Recording {
  id: string;
  name: string;
  folderId: string;
  recordedAt: string;
  duration: string;
  size: string;
  health: 'Readable' | 'Damaged';
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
  name: string;
  elapsed: number;
  duration: number;
  paused: boolean;
  cancelled: boolean;
}
export interface WorkspaceSnapshot {
  recordings: Recording[];
  queue: Job[];
  failures: Job[];
  history: Job[];
  active: ActiveJob;
}
export type Channel = `${'angular_velocity' | 'linear_acceleration'}.${'x' | 'y' | 'z'}`;
export interface Signal {
  values: number[];
  ticks: number[];
  unit: string;
  spokenUnit: string;
}
export interface AnalysisBundle {
  duration: number;
  startUnix: number;
  channels: Record<Channel, Signal>;
}
export type MoveDirection = 'earlier' | 'later';
export interface RecordingAsset {
  name: string;
  size: string;
  format: string;
  status: string;
}
export interface AnalysisRecording {
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
  cameras: { id: string; label: string; region: string; src: string; alt: string }[];
}
