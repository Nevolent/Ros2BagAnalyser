import { test, expect } from '@playwright/test';
import { createSyntheticWorkspace } from '../src/data/synthetic-workspace';

test('synthetic archive fills every view and gives each recording its own details', () => {
  const service = createSyntheticWorkspace(() => Date.parse('2026-09-24T12:00:00Z'));
  const state = service.getSnapshot();
  expect(state.recordings.length).toBeGreaterThan(500);
  expect(service.folders).toHaveLength(1);
  expect(service.folders[0].name).toBe('Recordings');
  expect(service.folders[0].children!.length).toBeGreaterThan(8);
  expect(state.queue).toHaveLength(14);
  expect(state.failures).toHaveLength(100);
  expect(state.history).toHaveLength(180);
  expect(state.recordings.some((row) => row.health === 'Damaged')).toBe(true);
  expect(state.recordings.some((row) => row.health === 'Review')).toBe(true);
  expect(state.recordings.some((row) => row.analysis === 'Not planned')).toBe(true);
  const first = state.recordings.find((row) => row.analysis === 'Ready')!;
  const second = state.recordings.find((row) => row.analysis === 'Not planned')!;
  service.loadAnalysis?.(first.id);
  const firstDetails = service.analysis!;
  service.loadAnalysis?.(second.id);
  const secondDetails = service.analysis!;
  expect(secondDetails.name).toBe(second.name);
  expect(secondDetails.info.find((field) => field.label === 'Source size')?.value).toBe(
    second.size,
  );
  expect(secondDetails.info.find((field) => field.label === 'Duration')?.value).toBe(
    second.duration,
  );
  expect(secondDetails.outputs[0].status).toBe('Not planned');
  expect(secondDetails.bundle).toBe(firstDetails.bundle);
  expect(secondDetails.cameras).toBe(firstDetails.cameras);
});

test('preparation, pause, completion, retry and cancellation advance the local queue', async () => {
  let time = Date.parse('2026-09-24T12:00:00Z');
  const service = createSyntheticWorkspace(() => time);
  const available = service
    .getSnapshot()
    .recordings.find(
      (row, index) =>
        row.analysis === 'Not planned' && row.health === 'Readable' && index % 11 !== 0,
    )!;
  const initialHistory = service.getSnapshot().history.length;
  expect(await service.prepare(new Set([available.id]))).toBe(true);
  expect(service.getSnapshot().queue[0].recordingId).toBe(available.id);
  expect(service.getSnapshot().recordings.find((row) => row.id === available.id)?.analysis).toBe(
    'Queued',
  );

  time += 30_000;
  service.tickPreview();
  const elapsed = service.getSnapshot().active.elapsed;
  await service.toggleProcessing();
  expect(service.getSnapshot().queue[0].readyIn).toBeNull();
  time += 90_000;
  service.tickPreview();
  expect(service.getSnapshot().active.elapsed).toBe(elapsed);
  await service.toggleProcessing();
  time += 34_000;
  service.tickPreview();
  expect(service.getSnapshot().active.name).toBe(available.name);
  expect(service.getSnapshot().recordings.find((row) => row.id === available.id)?.analysis).toBe(
    'Processing',
  );
  time += (service.getSnapshot().active.duration + 1) * 1000;
  service.tickPreview();
  expect(service.getSnapshot().recordings.find((row) => row.id === available.id)?.analysis).toBe(
    'Ready',
  );
  expect(service.getSnapshot().history.length).toBe(initialHistory + 1);

  const failed = service.getSnapshot().failures.find((job) => {
    const row = service.getSnapshot().recordings.find((item) => item.id === job.recordingId);
    return row?.health === 'Readable';
  })!;
  await service.retryJobs(new Set([failed.id]));
  expect(service.getSnapshot().queue[0].outputs).toBe(failed.failures!.length);
  expect(service.getSnapshot().failures.some((job) => job.id === failed.id)).toBe(false);
  const queued = service.getSnapshot().queue[1];
  await service.cancelJobs(new Set([queued.id]));
  expect(service.getSnapshot().queue.some((job) => job.id === queued.id)).toBe(false);
  expect(
    service.getSnapshot().recordings.find((row) => row.id === queued.recordingId)?.analysis,
  ).toBe('Not planned');
  await service.cancelProcessing();
  expect(service.getSnapshot().active.name).toBe(failed.name);
  time += (service.getSnapshot().active.duration + 1) * 1000;
  service.tickPreview();
  expect(
    service.getSnapshot().recordings.find((row) => row.id === failed.recordingId)?.analysis,
  ).toBe('Ready');
});
