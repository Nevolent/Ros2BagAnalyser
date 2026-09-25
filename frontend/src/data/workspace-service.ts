import type { MoveDirection, WorkspaceSnapshot, Folder, AnalysisRecording } from './types';

/** Local UI contract, independent of React and of any future HTTP transport. */
export interface WorkspaceService {
  readonly folders: Folder[];
  readonly analysis: AnalysisRecording | null;
  observe?(view: string): () => void;
  loadAnalysis?(id: string): () => void;
  rescan?(): Promise<boolean>;
  loadMore?(view: 'queued' | 'failed' | 'history'): Promise<void>;
  getSnapshot(): WorkspaceSnapshot;
  subscribe(listener: () => void): () => void;
  prepare(recordingIds: ReadonlySet<string>): void | Promise<boolean>;
  moveJobs(ids: ReadonlySet<string>, direction: MoveDirection): void | Promise<boolean>;
  cancelJobs(ids: ReadonlySet<string>): void | Promise<boolean>;
  retryJobs(ids: ReadonlySet<string>): void | Promise<boolean>;
  toggleProcessing(): void | Promise<boolean>;
  cancelProcessing(): void | Promise<boolean>;
  tickPreview(): void;
}
