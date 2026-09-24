import type { MoveDirection, WorkspaceSnapshot, Folder, AnalysisRecording } from './types';

/** Local UI contract, independent of React and of any future HTTP transport. */
export interface WorkspaceService {
  readonly folders: Folder[];
  readonly analysis: AnalysisRecording;
  getSnapshot(): WorkspaceSnapshot;
  subscribe(listener: () => void): () => void;
  prepare(recordingIds: ReadonlySet<string>): void;
  moveJobs(ids: ReadonlySet<string>, direction: MoveDirection): void;
  cancelJobs(ids: ReadonlySet<string>): void;
  retryJobs(ids: ReadonlySet<string>): void;
  toggleProcessing(): void;
  cancelProcessing(): void;
  tickPreview(): void;
}
