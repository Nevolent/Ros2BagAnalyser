import { folders as demoFolders } from './fixtures/folders';
import { createRecordings } from './fixtures/recordings';
import { analysisRecording as visualRecording } from './fixtures/recording-details';
import type {
  ActiveJob,
  AnalysisRecording,
  Folder,
  Job,
  Recording,
  WorkspaceSnapshot,
} from './types';
import type { WorkspaceService } from './workspace-service';

const sites = ['North range', 'South range', 'Lab fleet', 'Archive intake'];
const sessions = ['Morning runs', 'Night runs', 'Calibration', 'Regression'];
const issueCodes = [
  'E_SQLITE_INTEGRITY: database page 381 is malformed.',
  'E_MISSING_TOPIC: /camera/front/image_raw was not recorded.',
  'E_TIMESTAMP_ORDER: message time moved backwards after a recorder restart.',
  'E_VIDEO_DECODE: unsupported frame encoding bayer_rggb16.',
  'E_IMU_SCHEMA: angular velocity field is absent.',
  'E_STORAGE_READ: a bag chunk ended before its declared length.',
  'E_RENDER_TIMEOUT: preview generation exceeded the time limit.',
  'E_TRANSFORM_LOOKUP: map to base_link transform is unavailable.',
];

function archive(): { folders: Folder[]; recordings: Recording[] } {
  const folders: Folder[] = structuredClone(demoFolders);
  const validation = folders.find((folder) => folder.id === 'simulation');
  if (validation) validation.name = 'Validation';
  const recordings = createRecordings();
  sites.forEach((site, siteIndex) => {
    const children: Folder[] = [];
    sessions.forEach((session, sessionIndex) => {
      const folderId = 'synthetic-' + siteIndex + '-' + sessionIndex;
      children.push({ id: folderId, name: session });
      for (let run = 1; run <= 24; run++) {
        const number = siteIndex * 96 + sessionIndex * 24 + run;
        const recordedAt = new Date(
          Date.UTC(2026, 7 + (siteIndex % 2), 21 - (run % 18), 7 + (run % 11), (number * 7) % 60),
        );
        const stamp = recordedAt.toISOString().slice(0, 19).replace('T', '_').replaceAll(':', '-');
        const name =
          site.toLowerCase().replaceAll(' ', '_') +
          '_' +
          session.toLowerCase().replaceAll(' ', '_') +
          '_' +
          String(run).padStart(3, '0') +
          '_' +
          stamp +
          '.bag';
        recordings.push({
          id: name,
          name,
          folderId,
          recordedAt: recordedAt.toISOString(),
          duration:
            String(2 + ((number * 13) % 58)).padStart(2, '0') +
            ':' +
            String((number * 19) % 60).padStart(2, '0') +
            '.' +
            String((number * 137) % 1000).padStart(3, '0'),
          size: (0.35 + ((number * 1.17) % 19)).toFixed(2) + ' GB',
          health: number % 17 === 0 ? 'Damaged' : number % 23 === 0 ? 'Review' : 'Readable',
          analysis: 'Not planned',
        });
      }
    });
    folders.push({ id: 'synthetic-site-' + siteIndex, name: site, children });
  });
  return {
    folders: [{ id: 'synthetic-root', name: 'Recordings', children: folders }],
    recordings,
  };
}

function durationFor(index: number): number {
  return 60 + ((index * 17) % 61);
}

function failureFor(index: number) {
  const outputs = ['Front-camera preview', 'Top-down preview', 'IMU data bundle'];
  const count = index % 9 === 0 ? 3 : index % 5 === 0 ? 2 : 1;
  return Array.from({ length: count }, (_, offset) => ({
    output: outputs[(index + offset) % outputs.length],
    code: issueCodes[(index + offset) % issueCodes.length],
  }));
}

function updateRecording(
  rows: Recording[],
  id: string,
  analysis: Recording['analysis'],
): Recording[] {
  return rows.map((row) => (row.id === id ? { ...row, analysis } : row));
}

function details(row: Recording, failure?: Job): AnalysisRecording {
  const ready = row.analysis === 'Ready';
  const status = row.analysis;
  const issue = failure?.failures?.map((item) => item.code) ?? [];
  return {
    ...visualRecording,
    id: row.id,
    name: row.name,
    bundle: visualRecording.bundle,
    errors: [
      ...(row.health === 'Damaged' ? ['E_SQLITE_INTEGRITY: source recording is damaged.'] : []),
      ...(row.health === 'Review'
        ? ['Metadata reports zero duration; message timestamps need review.']
        : []),
      ...issue,
    ],
    info: visualRecording.info.map((field) => {
      if (field.label === 'Recorded')
        return { ...field, value: row.recordedAt, dateTime: row.recordedAt };
      if (field.label === 'Duration') return { ...field, value: row.duration };
      if (field.label === 'Source size') return { ...field, value: row.size };
      if (field.label === 'Messages')
        return { ...field, value: String(1300 + row.name.length * 137) };
      if (field.label === 'Topics') return { ...field, value: String(7 + (row.name.length % 14)) };
      if (field.label === 'ROS database') return { ...field, value: row.health };
      return field;
    }),
    outputs: visualRecording.outputs.map((output) => {
      const outputStatus =
        status === 'Failed' &&
        failure &&
        !failure.failures?.some((item) => item.output === output.name)
          ? 'Ready'
          : status;
      return {
        ...output,
        status: outputStatus,
        size: ready || outputStatus === 'Ready' ? output.size : '—',
      };
    }),
    sources: visualRecording.sources.map((source) => ({
      ...source,
      size: source.name === 'Rosbag' ? row.size : source.size,
      status: row.health === 'Damaged' ? 'Damaged' : 'Readable',
    })),
    cameras: visualRecording.cameras,
  };
}

/** Explicit in-memory archive and timed worker. No source or derived files are written. */
export function createSyntheticWorkspace(now = Date.now): WorkspaceService {
  const data = archive();
  const rows = data.recordings;
  for (const row of rows) {
    row.healthIssues =
      row.health === 'Damaged'
        ? ['E_SQLITE_INTEGRITY: source recording is damaged.']
        : row.health === 'Review'
          ? ['Metadata reports zero duration; message timestamps need review.']
          : [];
  }
  const start = now();
  const jobFor = (index: number, prefix: string): Job => ({
    id: prefix + '-' + index,
    recordingId: rows[index].id,
    name: rows[index].name,
    size: rows[index].size,
    queuedAt: start - index * 73000,
    duration: durationFor(index),
    outputs: 3,
  });
  const initialQueue = Array.from({ length: 14 }, (_, offset) => jobFor(offset + 1, 'queue'));
  const failures = Array.from({ length: 100 }, (_, offset) => {
    const index = offset + 15;
    return { ...jobFor(index, 'failure'), failures: failureFor(index) };
  });
  const history = Array.from({ length: 180 }, (_, offset) => {
    const index = offset + 115;
    const job = jobFor(index, 'history');
    return { ...job, completedAt: job.queuedAt + job.duration * 1000 };
  });
  rows[0].analysis = 'Processing';
  initialQueue.forEach((job) => {
    rows.find((row) => row.id === job.recordingId)!.analysis = 'Queued';
  });
  failures.forEach((job) => {
    rows.find((row) => row.id === job.recordingId)!.analysis = 'Failed';
  });
  history.forEach((job) => {
    rows.find((row) => row.id === job.recordingId)!.analysis = 'Ready';
  });
  const idle = (): ActiveJob => ({
    name: 'No active recording',
    elapsed: 0,
    duration: 0,
    paused: false,
    cancelled: false,
    idle: true,
  });
  let snapshot: WorkspaceSnapshot = {
    recordings: rows,
    queue: initialQueue,
    failures,
    history,
    active: { ...idle(), name: rows[0].name, idle: false, duration: 75, elapsed: 12 },
    lastScan: new Date(start).toISOString(),
  };
  let activeId: string | null = rows[0].id;
  let activeOutputCount = 3;
  const retriedIds = new Set<string>();
  let analysis: AnalysisRecording | null = null;
  let lastTick = start;
  let serial = 0;
  const listeners = new Set<() => void>();
  const publish = (patch: Partial<WorkspaceSnapshot>) => {
    snapshot = { ...snapshot, ...patch };
    if (analysis?.id) {
      const row = snapshot.recordings.find((item) => item.id === analysis?.id);
      if (row)
        analysis = details(
          row,
          snapshot.failures.find((item) => item.recordingId === row.id),
        );
    }
    listeners.forEach((listener) => listener());
  };
  const startNext = () => {
    const [next, ...queue] = snapshot.queue;
    if (!next) {
      activeId = null;
      publish({ queue: [], active: idle() });
      return;
    }
    activeId = next.recordingId ?? null;
    activeOutputCount = next.outputs;
    publish({
      queue,
      recordings: updateRecording(snapshot.recordings, activeId!, 'Processing'),
      active: { ...idle(), name: next.name, duration: next.duration, idle: false },
    });
  };
  const finish = () => {
    if (!activeId) return;
    const row = snapshot.recordings.find((item) => item.id === activeId)!;
    const index = snapshot.recordings.indexOf(row);
    const failed = row.health === 'Damaged' || (!retriedIds.has(row.id) && index % 11 === 0);
    retriedIds.delete(row.id);
    const job: Job = {
      id: 'completed-' + ++serial,
      recordingId: row.id,
      name: row.name,
      size: row.size,
      queuedAt: now() - snapshot.active.elapsed * 1000,
      duration: Math.round(snapshot.active.elapsed),
      outputs: activeOutputCount,
      completedAt: now(),
      ...(failed ? { failures: failureFor(index) } : {}),
    };
    publish({
      recordings: updateRecording(snapshot.recordings, row.id, failed ? 'Failed' : 'Ready'),
      failures: failed ? [job, ...snapshot.failures] : snapshot.failures,
      history: failed ? snapshot.history : [job, ...snapshot.history],
    });
    startNext();
  };
  const tick = () => {
    const current = now();
    let remaining = Math.max(0, (current - lastTick) / 1000);
    lastTick = current;
    if (snapshot.active.paused || (!activeId && !snapshot.queue.length)) return;
    while (remaining > 0) {
      if (!activeId) {
        if (!snapshot.queue.length) break;
        startNext();
      }
      const active = snapshot.active;
      const step = Math.min(remaining, Math.max(0, active.duration - active.elapsed));
      remaining -= step;
      const elapsed = active.elapsed + step;
      publish({ active: { ...active, elapsed } });
      if (elapsed >= active.duration) finish();
      else break;
    }
    let estimate = snapshot.active.idle ? 0 : snapshot.active.duration - snapshot.active.elapsed;
    publish({
      queue: snapshot.queue.map((job) => ({
        ...job,
        readyIn: snapshot.active.paused ? null : (estimate += job.duration),
      })),
    });
  };
  return {
    get folders() {
      return data.folders;
    },
    get analysis() {
      return analysis;
    },
    getSnapshot: () => snapshot,
    subscribe(listener) {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
    observe(view) {
      lastTick = now();
      const timer = setInterval(tick, view === 'processing' ? 1000 : 5000);
      return () => clearInterval(timer);
    },
    loadAnalysis(id) {
      const row = snapshot.recordings.find((item) => item.id === id);
      analysis = row
        ? details(
            row,
            snapshot.failures.find((item) => item.recordingId === id),
          )
        : null;
      publish({ analysisError: row ? '' : 'Recording not found.', analysisLoading: false });
      return () => {};
    },
    async rescan() {
      publish({ lastScan: new Date(now()).toISOString() });
      return true;
    },
    async prepare(ids) {
      const selected = snapshot.recordings.filter(
        (row) =>
          ids.has(row.id) &&
          row.analysis !== 'Ready' &&
          row.analysis !== 'Queued' &&
          row.analysis !== 'Processing',
      );
      if (!selected.length) return ids.size > 0;
      const additions: Job[] = selected.map((row) => ({
        id: 'prepared-' + ++serial,
        recordingId: row.id,
        name: row.name,
        queuedAt: now(),
        duration: durationFor(snapshot.recordings.indexOf(row)),
        size: row.size,
        outputs: 3,
      }));
      let recordings = snapshot.recordings;
      selected.forEach((row) => {
        recordings = updateRecording(recordings, row.id, 'Queued');
      });
      publish({ recordings, queue: [...additions, ...snapshot.queue], error: '' });
      if (!activeId) startNext();
      tick();
      return true;
    },
    moveJobs(ids, direction) {
      const queue = [...snapshot.queue];
      const delta = direction === 'earlier' ? -1 : 1;
      const indices = queue.map((_, index) => index);
      if (delta === 1) indices.reverse();
      for (const index of indices) {
        const neighbor = index + delta;
        if (ids.has(queue[index].id) && queue[neighbor] && !ids.has(queue[neighbor].id)) {
          [queue[index], queue[neighbor]] = [queue[neighbor], queue[index]];
        }
      }
      publish({ queue });
      tick();
    },
    async cancelJobs(ids) {
      const removed = snapshot.queue.filter((job) => ids.has(job.id));
      let recordings = snapshot.recordings;
      removed.forEach((job) => {
        recordings = updateRecording(recordings, job.recordingId!, 'Not planned');
      });
      publish({ recordings, queue: snapshot.queue.filter((job) => !ids.has(job.id)) });
      tick();
      return true;
    },
    async retryJobs(ids) {
      const retried = snapshot.failures.filter((job) => ids.has(job.id));
      let recordings = snapshot.recordings;
      retried.forEach((job) => {
        recordings = updateRecording(recordings, job.recordingId!, 'Queued');
        retriedIds.add(job.recordingId!);
      });
      publish({
        recordings,
        failures: snapshot.failures.filter((job) => !ids.has(job.id)),
        queue: [
          ...retried.map((job) => ({
            ...job,
            id: 'retry-' + ++serial,
            queuedAt: now(),
            outputs: job.failures?.length ?? job.outputs,
            failures: undefined,
          })),
          ...snapshot.queue,
        ],
      });
      tick();
      return true;
    },
    async toggleProcessing() {
      if (snapshot.active.idle) return false;
      tick();
      const paused = !snapshot.active.paused;
      publish({
        active: { ...snapshot.active, paused },
        queue: snapshot.queue.map((job) => ({ ...job, readyIn: paused ? null : job.readyIn })),
      });
      if (!paused) tick();
      return true;
    },
    async cancelProcessing() {
      if (!activeId) return false;
      const id = activeId;
      publish({ recordings: updateRecording(snapshot.recordings, id, 'Not planned') });
      startNext();
      return true;
    },
    tickPreview: tick,
  };
}
