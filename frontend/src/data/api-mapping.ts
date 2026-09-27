import type { ActiveJob, Folder, Job, Recording } from './types';
import type { ApiJob, Catalog, CatalogRecording, Kind, Overview } from './api-types';
export const outputNames: Record<Kind, string> = {
  front_preview: 'Front-camera preview',
  topdown_preview: 'Top-down preview',
  imu_series: 'IMU data bundle',
};
export const labels: Record<string, string> = {
  ready: 'Ready',
  failed: 'Failed',
  queued: 'Queued',
  processing: 'Processing',
  not_planned: 'Not planned',
  not_requested: 'Not planned',
  unavailable: 'Unavailable',
};
export function seconds(ns: string | null | undefined): number {
  if (ns == null) return 0;
  if (!/^-?\d+$/.test(ns)) throw new Error('Invalid recording timestamp.');
  return Number(BigInt(ns)) / 1e9;
}
export function bytes(value: string | null | undefined): string {
  if (value == null) return '—';
  const size = Number(value);
  if (!Number.isFinite(size) || size < 0) return '—';
  const unit = size > 0 ? Math.min(4, Math.floor(Math.log(size) / Math.log(1024))) : 0;
  return `${(size / 1024 ** unit).toFixed(unit ? 2 : 0)} ${['B', 'KiB', 'MiB', 'GiB', 'TiB'][unit]}`;
}
export function duration(ns: string | null): string {
  if (ns === null) return '—';
  const ms = Math.max(0, Math.floor(seconds(ns) * 1000));
  return `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}.${String(ms % 1000).padStart(3, '0')}`;
}
export function recording(row: CatalogRecording): Recording {
  if (
    !Number.isSafeInteger(row.id) ||
    row.id < 1 ||
    typeof row.name !== 'string' ||
    !Array.isArray(row.outputs)
  )
    throw new Error('Invalid catalog response.');
  return {
    id: String(row.id),
    name: row.name,
    folderId: row.folder_path,
    recordedAt:
      row.start_time_ns === null ? '' : new Date(seconds(row.start_time_ns) * 1000).toISOString(),
    duration: duration(row.duration_ns),
    size: bytes(row.total_source_size_bytes),
    health:
      row.presentation_health !== 'readable'
        ? 'Damaged'
        : row.duration_ns === '0'
          ? 'Review'
          : 'Readable',
    analysis: row.outputs.some((output) => output.state === 'failed')
      ? 'Failed'
      : row.analysis_state === 'not_planned' &&
          row.outputs.some((output) => output.state === 'ready')
        ? 'Ready'
        : ((labels[row.analysis_state] as Recording['analysis']) ?? 'Not planned'),
  };
}
export function folders(rows: Catalog['folders']): Folder[] {
  const byPath = new Map(
    rows
      .filter((row) => row.path)
      .map((row) => [row.path, { id: row.path, name: row.name } as Folder]),
  );
  const roots: Folder[] = [];
  for (const row of rows) {
    const item = byPath.get(row.path);
    if (!item) continue;
    const parent = byPath.get(row.parent_path);
    if (parent && parent !== item) (parent.children ??= []).push(item);
    else roots.push(item);
  }
  return roots;
}
export function jobs(rows: ApiJob[], group: boolean): Job[] {
  const result = new Map<string, Job>();
  const sizes = new Map<string, bigint | null>();
  for (const row of rows) {
    const key = String(group ? row.recording_id : row.id);
    const existing = result.get(key);
    const failure = row.diagnostic
      ? [
          {
            output: outputNames[row.kind],
            code: `${row.diagnostic.code}: ${row.diagnostic.message}`,
          },
        ]
      : row.state === 'failed'
        ? [{ output: outputNames[row.kind], code: 'Processing failed.' }]
        : [];
    const readyIn =
      row.queue_estimate?.status === 'available' && row.queue_estimate.ready_in_ms !== null
        ? row.queue_estimate.ready_in_ms / 1000
        : null;
    if (existing) {
      existing.jobIds!.push(row.id);
      existing.outputs += 1;
      existing.duration += (row.runtime_ms ?? 0) / 1000;
      existing.runtimeKnown = existing.runtimeKnown && row.runtime_ms !== null;
      existing.queuedAt = Math.min(existing.queuedAt, Date.parse(row.queued_at));
      existing.completedAt =
        Math.max(existing.completedAt ?? 0, row.finished_at ? Date.parse(row.finished_at) : 0) ||
        undefined;
      const total = sizes.get(key);
      sizes.set(
        key,
        total == null || row.output_size_bytes === null
          ? null
          : total + BigInt(row.output_size_bytes),
      );
      existing.size = bytes(sizes.get(key)?.toString());
      existing.failures!.push(...failure);
      existing.readyIn =
        existing.readyIn === null || readyIn === null ? null : Math.max(existing.readyIn!, readyIn);
      existing.canCancel = existing.canCancel && row.allowed_controls.includes('cancel');
    } else {
      sizes.set(key, row.output_size_bytes === null ? null : BigInt(row.output_size_bytes));
      result.set(key, {
        id: key,
        jobIds: [row.id],
        recordingId: String(row.recording_id),
        name: row.recording_name,
        queuedAt: Date.parse(row.queued_at),
        completedAt: row.finished_at ? Date.parse(row.finished_at) : undefined,
        duration: (row.runtime_ms ?? 0) / 1000,
        runtimeKnown: row.runtime_ms !== null,
        outputs: 1,
        size: bytes(row.output_size_bytes),
        failures: failure,
        readyIn,
        canCancel: row.allowed_controls.includes('cancel'),
      });
    }
  }
  return [...result.values()];
}
export function activeJob(overview: Overview): ActiveJob {
  const row = overview.current;
  if (!row)
    return {
      name: 'No active job',
      elapsed: 0,
      duration: 0,
      paused: false,
      cancelled: false,
      live: true,
      idle: true,
      status: overview.worker_online ? '' : 'Worker is offline.',
    };
  return {
    id: row.id,
    recordingId: row.recording_id,
    name: row.recording_name,
    elapsed: (row.active_elapsed_ms ?? row.elapsed_ms ?? 0) / 1000,
    duration: (row.estimate?.estimated_total_ms ?? 0) / 1000,
    paused: row.control_state === 'paused',
    pendingPause: row.control_state === 'pause_requested',
    cancelled: row.control_state === 'cancel_requested',
    live: true,
    estimateStatus: row.estimate?.status ?? 'unavailable',
    controls: row.allowed_controls,
    status: overview.worker_online ? '' : 'Worker is offline.',
  };
}

/** A recording with an actionable failure keeps all its outputs in Failures. */
export function processingGroups(
  queue: ApiJob[],
  failures: ApiJob[],
  history: ApiJob[],
  current: ApiJob | null,
  totals = new Map<number, number>(),
) {
  const failedRecordings = new Map<number, number[]>();
  for (const row of failures) {
    const ids = failedRecordings.get(row.recording_id) ?? [];
    ids.push(row.id);
    failedRecordings.set(row.recording_id, ids);
  }
  const outputs = new Map<string, ApiJob>();
  // Prefer current work/failures over an older successful attempt of the same output.
  for (const row of [...history, ...queue, ...(current ? [current] : []), ...failures]) {
    if (failedRecordings.has(row.recording_id)) outputs.set(`${row.recording_id}:${row.kind}`, row);
  }
  const grouped = jobs([...outputs.values()], true);
  const byRecording = new Map(grouped.map((job) => [job.recordingId, job]));
  return {
    failures: [...failedRecordings].map(([id, jobIds]) => {
      const group = byRecording.get(String(id))!;
      return {
        ...group,
        outputs: Math.max(group.outputs, totals.get(id) ?? 0),
        jobIds,
      };
    }),
    history: jobs(
      history.filter((row) => !failedRecordings.has(row.recording_id)),
      true,
    ),
  };
}
