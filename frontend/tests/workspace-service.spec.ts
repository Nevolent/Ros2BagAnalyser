import { test, expect } from '@playwright/test';
import { createDemoWorkspace } from '../src/data/demo-workspace';

test('preparing is atomic, deduplicates queued recordings, and cancellation updates the archive', () => {
  const service = createDemoWorkspace(() => Date.parse('2026-09-21T09:00:00Z'));
  const initial = service.getSnapshot();
  const recording = initial.recordings[0];
  let notifications = 0;
  const unsubscribe = service.subscribe(() => notifications++);
  service.prepare(new Set([recording.id]));
  const prepared = service.getSnapshot();
  expect(prepared.recordings.find((item) => item.id === recording.id)?.analysis).toBe('Queued');
  expect(initial.recordings[0].analysis).toBe('Ready');
  expect(notifications).toBe(1);
  service.prepare(new Set([recording.id]));
  expect(service.getSnapshot().queue.filter((job) => job.name === recording.name)).toHaveLength(1);
  const job = service.getSnapshot().queue.find((job) => job.name === recording.name)!;
  service.cancelJobs(new Set([job.id]));
  expect(service.getSnapshot().recordings[0].analysis).toBe('Not planned');
  expect(service.getSnapshot().queue.some((item) => item.id === job.id)).toBe(false);
  unsubscribe();
  const count = notifications;
  service.prepare(new Set([recording.id]));
  expect(notifications).toBe(count);
});

test('group moves retain order and snapshots; retries preserve only failed outputs', () => {
  const service = createDemoWorkspace(() => 1000);
  const original = service.getSnapshot();
  const ids = original.queue.map((job) => job.id);
  service.moveJobs(new Set([ids[1], ids[2]]), 'earlier');
  expect(service.getSnapshot().queue.map((job) => job.id)).toEqual([
    ids[1],
    ids[2],
    ids[0],
    ids[3],
  ]);
  expect(original.queue.map((job) => job.id)).toEqual(ids);
  const failure = original.failures[1];
  service.retryJobs(new Set([failure.id]));
  const retried = service.getSnapshot().queue.find((job) => job.id === failure.id)!;
  expect(retried.outputs).toBe(failure.failures!.length);
  expect(retried.failures).toBeUndefined();
  expect(retried.queuedAt).toBe(1000);
  service.retryJobs(new Set([failure.id]));
  expect(service.getSnapshot().queue.filter((job) => job.id === failure.id)).toHaveLength(1);
  expect(original.failures).toHaveLength(3);
});
