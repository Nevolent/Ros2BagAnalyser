import type { WorkspaceService } from './workspace-service';
import type { AnalysisRecording, Folder, Job, WorkspaceSnapshot } from './types';
import type { Catalog, Detail, JobsPage, Overview } from './api-types';
import { activeJob, folders, jobs, recording } from './api-mapping';
import { analysisRecording } from './analysis-adapter';
import { errorMessage, numericId, request } from './http';
type View = 'queued' | 'failed' | 'history';
export function createApiWorkspace(): WorkspaceService {
  let snapshot: WorkspaceSnapshot = {
    recordings: [],
    queue: [],
    failures: [],
    history: [],
    loading: true,
    active: {
      name: '',
      elapsed: 0,
      duration: 0,
      paused: false,
      cancelled: false,
      live: true,
      idle: true,
    },
  };
  let folderTree: Folder[] = [];
  let analysis: AnalysisRecording | null = null;
  let currentView = 'recordings';
  let epoch = 0;
  let actionError = '';
  let pollMs = 3000;
  const pages: Record<View, number> = { queued: 1, failed: 1, history: 1 };
  const listeners = new Set<() => void>();
  function publish(patch: Partial<WorkspaceSnapshot>) {
    snapshot = { ...snapshot, ...patch };
    listeners.forEach((listener) => listener());
  }
  async function readJobs(view: View, signal?: AbortSignal) {
    const items: JobsPage['items'] = [];
    const seen = new Set<string>();
    let cursor: string | null = null;
    for (let page = 0; page < pages[view]; page++) {
      const params = new URLSearchParams({ view, limit: '100' });
      if (cursor) params.set('cursor', cursor);
      const result: JobsPage = await request(`/api/v1/processing/jobs?${params}`, signal);
      if (!Array.isArray(result.items)) throw new Error('Invalid processing response.');
      items.push(...result.items);
      cursor = result.next_cursor;
      if (!cursor) break;
      if (seen.has(cursor)) throw new Error('Invalid processing cursor.');
      seen.add(cursor);
    }
    return { rows: [...new Map(items.map((job) => [job.id, job])).values()], more: !!cursor };
  }
  async function refresh(signal?: AbortSignal) {
    const version = epoch,
      view = currentView;
    try {
      if (view === 'processing') {
        const [overview, queue, failed, history] = await Promise.all([
          request<Overview>('/api/v1/processing/overview', signal),
          readJobs('queued', signal),
          readJobs('failed', signal),
          readJobs('history', signal),
        ]);
        if (version !== epoch || signal?.aborted || view !== currentView) return;
        pollMs = Math.min(30000, Math.max(1000, overview.recommended_poll_interval_ms || 3000));
        const estimates = new Map(
          (overview.queue ?? []).map((job) => [job.id, job.queue_estimate]),
        );
        const queued = queue.rows
          .filter((job) => job.recording_id !== overview.current?.recording_id)
          .map((job) => ({ ...job, queue_estimate: estimates.get(job.id) ?? job.queue_estimate }));
        publish({
          queue: jobs(queued, true),
          failures: jobs(failed.rows, true),
          history: jobs(history.rows, true),
          active: activeJob(overview),
          loading: false,
          error: actionError,
          more: { queued: queue.more, failed: failed.more, history: history.more },
        });
      } else if (view === 'recordings') {
        const data = await request<Catalog>('/api/v1/catalog', signal);
        const rows = data.recordings.map(recording);
        const tree = folders(data.folders);
        if (version !== epoch || signal?.aborted || view !== currentView) return;
        folderTree = tree;
        publish({
          recordings: rows,
          lastScan: data.scan.completed_at,
          loading: false,
          error: actionError,
        });
      }
    } catch (error) {
      if (signal?.aborted || version !== epoch) return;
      publish({ loading: false, error: errorMessage(error) });
      pollMs = Math.min(30000, pollMs * 2);
    }
  }
  async function mutate(path: string, body: unknown = {}, scanning = false): Promise<boolean> {
    if (snapshot.busy) return false;
    epoch++;
    actionError = '';
    publish({ busy: true, error: '', scanning });
    try {
      const payload = typeof body === 'function' ? await body() : body;
      const result = await request<{
        items?: { outcome: string; diagnostic?: { code?: string; message: string } | null }[];
        recordings?: {
          outputs: { outcome: string; diagnostic?: { code?: string; message: string } | null }[];
        }[];
        outcome?: string;
      }>(path, undefined, payload);
      const items =
        result.items ??
        result.recordings?.flatMap((item) => item.outputs) ??
        (result.outcome ? [{ outcome: result.outcome }] : []);
      const rejected = items.filter(
        (item) =>
          !['topdown_video_unavailable', 'topdown_timestamps_unavailable'].includes(
            item.diagnostic?.code ?? '',
          ) &&
          [
            'conflict',
            'not_found',
            'unavailable',
            'rejected',
            'invalid_state',
            'request_failed',
          ].includes(item.outcome),
      );
      await refresh();
      if (rejected.length) {
        actionError = rejected
          .map((item) => item.diagnostic?.message ?? `Action ${item.outcome.replaceAll('_', ' ')}.`)
          .join(' ');
        publish({ error: actionError });
        return false;
      }
      return true;
    } catch (error) {
      actionError = errorMessage(error);
      publish({ error: actionError });
      return false;
    } finally {
      publish({ busy: false, scanning: false });
    }
  }
  function selectedJobs(ids: ReadonlySet<string>, rows: Job[]) {
    return rows.filter((job) => ids.has(job.id)).flatMap((job) => job.jobIds ?? []);
  }
  return {
    get folders() {
      return folderTree;
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
      currentView = view;
      epoch++;
      actionError = '';
      const controller = new AbortController();
      let timer: ReturnType<typeof setTimeout>;
      publish({ loading: view !== 'analysis', error: '' });
      let running = false;
      const poll = async () => {
        if (running || controller.signal.aborted) return;
        running = true;
        clearTimeout(timer);
        if (!snapshot.busy && !document.hidden) await refresh(controller.signal);
        running = false;
        if (!controller.signal.aborted) timer = setTimeout(poll, pollMs);
      };
      const visible = () => {
        if (!document.hidden) {
          clearTimeout(timer);
          void poll();
        }
      };
      document.addEventListener('visibilitychange', visible);
      void poll();
      return () => {
        controller.abort();
        clearTimeout(timer);
        document.removeEventListener('visibilitychange', visible);
      };
    },
    loadAnalysis(id) {
      const controller = new AbortController();
      let timer: ReturnType<typeof setTimeout>;
      if (analysis?.id !== id) analysis = null;
      publish({ analysisLoading: true, analysisError: '' });
      const poll = async () => {
        try {
          const number = numericId(id);
          const detail = await request<Detail>(`/api/v1/recordings/${number}`, controller.signal);
          if (detail.id !== number) throw new Error('Recording identity does not match.');
          const next = await analysisRecording(detail, controller.signal, analysis);
          if (controller.signal.aborted) return;
          // Preserve the playback clock and chart memoization when only job metadata changed.
          if (
            analysis?.id === id &&
            analysis.bundle.channels === next.bundle.channels &&
            analysis.bundle.duration === next.bundle.duration &&
            analysis.bundle.mediaVersion === next.bundle.mediaVersion
          )
            next.bundle = analysis.bundle;
          analysis = next;
          publish({ analysisLoading: false, analysisError: '' });
        } catch (error) {
          if (controller.signal.aborted) return;
          publish({ analysisLoading: false, analysisError: errorMessage(error) });
        }
        if (!controller.signal.aborted) timer = setTimeout(poll, 3000);
      };
      void poll();
      return () => {
        controller.abort();
        clearTimeout(timer);
      };
    },
    async loadMore(view) {
      pages[view] += 1;
      await refresh();
    },
    rescan: () => mutate('/api/v1/catalog/rescan', {}, true),
    prepare: (ids) =>
      mutate('/api/v1/recordings/prepare', {
        recording_ids: [...ids].map(numericId),
        output_kinds: ['front_preview', 'topdown_preview', 'imu_series'],
      }),
    cancelJobs: (ids) =>
      mutate('/api/v1/processing/jobs/cancel', { job_ids: selectedJobs(ids, snapshot.queue) }),
    retryJobs: (ids) =>
      mutate('/api/v1/processing/jobs/retry', { job_ids: selectedJobs(ids, snapshot.failures) }),
    toggleProcessing: () => {
      const job = snapshot.active;
      const action = job.paused ? 'resume' : 'pause';
      return job.id && job.controls?.includes(action)
        ? mutate(`/api/v1/processing/jobs/${job.id}/${action}`)
        : Promise.resolve(false);
    },
    cancelProcessing: () => {
      const active = snapshot.active;
      if (!active.id || !active.recordingId || !active.controls?.includes('cancel'))
        return Promise.resolve(false);
      return mutate('/api/v1/processing/jobs/cancel', async () => {
        const detail = await request<Detail>(`/api/v1/recordings/${active.recordingId}`);
        if (detail.id !== active.recordingId) throw new Error('Recording identity does not match.');
        const ids = detail.outputs
          .filter((output) => ['processing', 'queued'].includes(output.state) && output.job_id)
          .map((output) => output.job_id!);
        return { job_ids: [...new Set([active.id!, ...ids])] };
      });
    },
    moveJobs: () => {},
    tickPreview: () => {},
  };
}
