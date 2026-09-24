import type { Job, MoveDirection } from '../data/types';

export function canMoveJobs(queue: Job[], ids: ReadonlySet<string>, direction: MoveDirection) {
  const delta = direction === 'earlier' ? -1 : 1;
  return queue.some(
    (job, index) => ids.has(job.id) && queue[index + delta] && !ids.has(queue[index + delta].id),
  );
}
