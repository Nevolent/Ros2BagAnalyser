import { folders } from './fixtures/folders';
import { analysisRecording } from './fixtures/recording-details';
import { createRecordings } from './fixtures/recordings';
import { createProcessing } from './fixtures/processing';
import type { WorkspaceSnapshot, Job } from './types';
import type { WorkspaceService } from './workspace-service';

/** Session-only data. Construct once per app; reloading restores the fixtures. */
export function createDemoWorkspace(now = Date.now): WorkspaceService {
  let snapshot: WorkspaceSnapshot = {
    recordings: createRecordings().map((row) => ({
      ...row,
      analysisIssues:
        row.analysis === 'Failed'
          ? ['Front-camera preview: E_VIDEO_DECODE: unsupported frame encoding bayer_rggb16.']
          : [],
    })),
    ...createProcessing(now()),
  };
  const listeners = new Set<() => void>();
  const publish = (next: WorkspaceSnapshot) => {
    snapshot = next;
    listeners.forEach((listener) => listener());
  };
  return {
    folders,
    analysis: analysisRecording,
    getSnapshot: () => snapshot,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    prepare(ids) {
      const selected = snapshot.recordings.filter((recording) => ids.has(recording.id));
      const existing = new Set(snapshot.queue.map((job) => job.name));
      const additions: Job[] = selected
        .filter((recording) => !existing.has(recording.name))
        .map((recording) => ({
          id: `prepared-${recording.id}`,
          name: recording.name,
          size: recording.size,
          queuedAt: now(),
          duration: 221,
          outputs: 3,
        }));
      publish({
        ...snapshot,
        queue: [...snapshot.queue, ...additions],
        recordings: snapshot.recordings.map((recording) =>
          ids.has(recording.id) ? { ...recording, analysis: 'Queued' } : recording,
        ),
      });
    },
    moveJobs(ids, direction) {
      const queue = [...snapshot.queue];
      const delta = direction === 'earlier' ? -1 : 1;
      const indices = queue.map((_, index) => index);
      if (delta === 1) indices.reverse();
      for (const index of indices) {
        const other = index + delta;
        if (ids.has(queue[index].id) && queue[other] && !ids.has(queue[other].id)) {
          [queue[index], queue[other]] = [queue[other], queue[index]];
        }
      }
      publish({ ...snapshot, queue });
    },
    cancelJobs(ids) {
      const names = new Set(snapshot.queue.filter((job) => ids.has(job.id)).map((job) => job.name));
      publish({
        ...snapshot,
        queue: snapshot.queue.filter((job) => !ids.has(job.id)),
        recordings: snapshot.recordings.map((recording) =>
          names.has(recording.name) && recording.analysis === 'Queued'
            ? { ...recording, analysis: 'Not planned' }
            : recording,
        ),
      });
    },
    retryJobs(ids) {
      const retried = snapshot.failures.filter((job) => ids.has(job.id));
      publish({
        ...snapshot,
        failures: snapshot.failures.filter((job) => !ids.has(job.id)),
        queue: [
          ...snapshot.queue,
          ...retried.map((job) => ({
            ...job,
            outputs: job.failures!.length,
            failures: undefined,
            queuedAt: now(),
          })),
        ],
      });
    },
    toggleProcessing() {
      publish({ ...snapshot, active: { ...snapshot.active, paused: !snapshot.active.paused } });
    },
    cancelProcessing() {
      publish({ ...snapshot, active: { ...snapshot.active, cancelled: true } });
    },
    tickPreview() {
      const { active } = snapshot;
      if (active.paused || active.cancelled) return;
      publish({
        ...snapshot,
        active: { ...active, elapsed: active.elapsed >= active.duration ? 0 : active.elapsed + 1 },
      });
    },
  };
}
