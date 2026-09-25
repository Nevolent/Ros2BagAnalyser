import { ActiveJobCard } from './ActiveJobCard';
import { Tabs } from '../../components/Tabs';
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useWorkspace, useWorkspaceService } from '../../app/WorkspaceProvider';
import type { Job, MoveDirection } from '../../data/types';
import { formatDuration, formatJobDate } from '../../lib/format';
import { Page } from '../../components/Page';
import { Checkbox } from '../../components/Checkbox';
import { Dialog } from '../../components/Dialog';
import { EmptyState, TableBody, TablePanel } from '../../components/DataTable';
import { Icon } from '../../components/Icon';

import { SortableHeader } from '../../components/SortableHeader';
import { useTableSort, sizeInBytes } from '../../lib/useTableSort';
import { canMoveJobs } from '../../lib/queue';

type View = 'queue' | 'failures' | 'history';
type Action = 'cancel' | 'retry';
const columns: Record<View, { labels: string[]; classes: string[]; region: string }> = {
  queue: {
    labels: ['Name', 'Queued', 'Ready in', 'Outputs', 'Actions'],
    classes: [
      '',
      'bag-recorded-column',
      'processing-ready-column',
      'processing-outputs-column',
      'processing-actions-column',
    ],
    region: 'Queued jobs',
  },
  failures: {
    labels: ['Name', 'Failed outputs', 'Error code', 'Actions'],
    classes: [
      'processing-failed-name-column',
      'processing-failed-count-column',
      'processing-error-column',
      'processing-retry-column',
    ],
    region: 'Failed jobs',
  },
  history: {
    labels: ['Name', 'Completed', 'Runtime', 'Size', 'Outputs'],
    classes: [
      '',
      'bag-recorded-column',
      'bag-duration-column',
      'bag-size-column',
      'processing-history-outputs-column',
    ],
    region: 'Completed jobs',
  },
};
function JobTime({ timestamp }: { timestamp: number }) {
  return (
    <time
      dateTime={new Date(timestamp).toISOString()}
      title={`${formatJobDate(timestamp)} · Europe/Tallinn`}
    >
      {formatJobDate(timestamp)}
    </time>
  );
}
function formatReadyIn(seconds: number) {
  const minutes = Math.max(1, Math.ceil(seconds / 60));
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours} hr ${remainder} min` : `${hours} hr`;
}
export function ProcessingPage() {
  const service = useWorkspaceService();
  const { queue, failures, history, active, loading, error, busy, more } = useWorkspace();
  const [view, setView] = useState<View>('queue');
  const [selection, setSelection] = useState(new Set<string>());
  const [notice, setNotice] = useState('');
  const [cancel, setCancel] = useState<{ active: boolean; ids: Set<string> } | null>(null);
  const [failure, setFailure] = useState<Job | null>(null);
  const tbody = useRef<HTMLTableSectionElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const queueTab = useRef<HTMLButtonElement>(null);
  const previousQueuePositions = useRef<Map<string, number> | null>(null);
  const items = view === 'queue' ? queue : view === 'failures' ? failures : history;
  useEffect(() => {
    setSelection((current) => {
      const next = new Set([...current].filter((id) => items.some((row) => row.id === id)));
      return next.size === current.size ? current : next;
    });
  }, [items]);
  useLayoutEffect(() => {
    const previous = previousQueuePositions.current;
    if (!previous || view !== 'queue') return;
    previousQueuePositions.current = null;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    tbody.current?.querySelectorAll<HTMLTableRowElement>('tr[data-job-id]').forEach((row) => {
      const before = previous.get(row.dataset.jobId ?? '');
      if (before === undefined) return;
      const offset = before - row.getBoundingClientRect().top;
      if (Math.abs(offset) < 1) return;
      row.animate([{ transform: `translateY(${offset}px)` }, { transform: 'translateY(0)' }], {
        duration: 320,
        easing: 'cubic-bezier(.22, 1, .36, 1)',
      });
    });
  }, [queue, view]);
  const selectable = view !== 'history';
  const config = columns[view];
  const readyIn = useMemo(() => {
    let estimate = active.cancelled ? 0 : active.duration - active.elapsed;
    return new Map(queue.map((job) => [job.id, (estimate += job.duration)]));
  }, [queue, active.cancelled, active.elapsed === 0]);
  const accessors = useMemo(
    () => ({
      Name: (job: Job) => job.name,
      Queued: (job: Job) => job.queuedAt,
      'Ready in': (job: Job) =>
        job.readyIn === undefined ? (readyIn.get(job.id) ?? 0) : (job.readyIn ?? Infinity),
      Outputs: (job: Job) => job.outputs,
      'Failed outputs': (job: Job) => job.failures?.length ?? 0,
      'Error code': (job: Job) => job.failures?.[0]?.code ?? '',
      Completed: (job: Job) => job.completedAt ?? 0,
      Runtime: (job: Job) => job.duration,
      Size: (job: Job) => sizeInBytes(job.size),
    }),
    [readyIn],
  );
  const { sorted, sort, toggle, reset: resetSort } = useTableSort(items, accessors);
  useEffect(() => {
    if (service.observe) return;
    const timer = setInterval(service.tickPreview, 1000);
    return () => clearInterval(timer);
  }, [service]);
  function select(id: string, checked: boolean) {
    setSelection((current) => {
      const next = new Set(current);
      checked ? next.add(id) : next.delete(id);
      return next;
    });
  }
  async function act(action: Action, ids: Set<string>) {
    if (!ids.size || busy) return;
    if (action === 'retry') {
      if ((await service.retryJobs(ids)) === false) return;
      setSelection(new Set());
      setNotice('Retry request completed.');
    } else setCancel({ active: false, ids });
  }
  async function move(direction: MoveDirection) {
    if (busy || !canMoveJobs(queue, selection, direction)) return;
    previousQueuePositions.current = new Map(
      [...(tbody.current?.querySelectorAll<HTMLTableRowElement>('tr[data-job-id]') ?? [])].map(
        (row) => [row.dataset.jobId!, row.getBoundingClientRect().top],
      ),
    );
    const beforeOrder = queue.map((job) => job.id).join('\0');
    resetSort();
    const moved = await service.moveJobs(new Set(selection), direction);
    if (moved === false) previousQueuePositions.current = null;
    else {
      const changed =
        service
          .getSnapshot()
          .queue.map((job) => job.id)
          .join('\0') !== beforeOrder;
      setNotice(
        changed
          ? `${selection.size} ${selection.size === 1 ? 'job' : 'jobs'} moved ${direction}.`
          : 'Queue order unchanged.',
      );
    }
  }
  function actionButton(job: Job, action: Action, label: string, disabled = false) {
    return (
      <button
        type="button"
        data-job-action={action}
        aria-label={`${label} ${job.name}`}
        title={label}
        disabled={disabled || busy}
        onClick={() => act(action, new Set([job.id]))}
      >
        <Icon name={action} strokeWidth={1.75} />
      </button>
    );
  }
  const cancelCount = cancel?.active ? 1 : (cancel?.ids.size ?? 0);
  return (
    <Page name="processing" title="Processing">
      <div className="dashboard-workspace processing-workspace">
        <ActiveJobCard
          active={active}
          onToggle={() => void service.toggleProcessing()}
          busy={busy}
          onCancel={() => setCancel({ active: true, ids: new Set() })}
        />
        <TablePanel
          className="processing-table-panel"
          aria-label="Processing jobs"
          data-processing-table=""
        >
          <div className="bag-panel-header">
            <Tabs
              label="Processing views"
              items={[
                { value: 'queue', label: 'Queue', count: queue.length },
                { value: 'failures', label: 'Failures', count: failures.length },
                { value: 'history', label: 'History', count: history.length },
              ]}
              value={view}
              controls="processing-table-body"
              firstRef={queueTab}
              onChange={(tab: View) => {
                setView(tab);
                resetSort();
                setSelection(new Set());
                if (scroll.current) scroll.current.scrollTop = scroll.current.scrollLeft = 0;
              }}
            />
            <div
              className="processing-bulk-actions"
              role="group"
              aria-label="Selected jobs"
              hidden={!selection.size}
            >
              {view === 'queue' &&
                (['earlier', 'later'] as const).map((direction) => (
                  <button
                    key={direction}
                    type="button"
                    data-bulk-action={direction}
                    disabled={busy || !canMoveJobs(queue, selection, direction)}
                    onClick={() => void move(direction)}
                  >
                    <span>{direction === 'earlier' ? 'Move up' : 'Move down'}</span>
                    <Icon name={direction} strokeWidth={1.75} />
                  </button>
                ))}
              <button
                type="button"
                data-bulk-action={view === 'failures' ? 'retry' : 'cancel'}
                disabled={busy}
                onClick={() => act(view === 'failures' ? 'retry' : 'cancel', new Set(selection))}
              >
                <span>
                  {view === 'failures'
                    ? `Retry ${selection.size} selected`
                    : `Cancel ${selection.size} selected`}
                </span>
                <Icon name={view === 'failures' ? 'retry' : 'cancel'} strokeWidth={1.75} />
              </button>
            </div>
          </div>
          <p className="inline-error" role="alert" hidden={!error}>
            {error}
          </p>
          <TableBody
            id="processing-table-body"
            label={config.region}
            scrollRef={scroll}
            empty={
              <EmptyState
                data-processing-empty=""
                hidden={!loading && (items.length > 0 || !!error)}
              >
                {loading
                  ? 'Loading processing…'
                  : view === 'queue'
                    ? 'No queued jobs.'
                    : view === 'failures'
                      ? 'No failed jobs.'
                      : 'No completed jobs yet.'}
              </EmptyState>
            }
          >
            <table className={`bag-table${view === 'queue' ? ' processing-queue-table' : ''}`}>
              <caption className="sr-only">
                {config.region}. All times are in Europe/Tallinn.
              </caption>
              <colgroup>
                {selectable && <col className="bag-select-column" />}
                {config.classes.map((name, i) => (
                  <col key={i} className={name} />
                ))}
              </colgroup>
              <thead>
                <tr>
                  {selectable && (
                    <th scope="col" className="bag-select-cell">
                      <Checkbox
                        data-job-select-all=""
                        aria-label={`Select all ${view === 'queue' ? 'queued' : 'failed'} jobs`}
                        checked={items.length > 0 && selection.size === items.length}
                        indeterminate={selection.size > 0 && selection.size < items.length}
                        disabled={!items.length}
                        onChange={(event) =>
                          setSelection(
                            event.target.checked ? new Set(items.map((job) => job.id)) : new Set(),
                          )
                        }
                      />
                    </th>
                  )}
                  {config.labels.map((label) =>
                    label === 'Actions' ? (
                      <th scope="col" key={label} className="processing-actions-heading">
                        {label}
                      </th>
                    ) : (
                      <SortableHeader
                        column={label as keyof typeof accessors}
                        sort={sort}
                        onSort={toggle}
                        scope="col"
                        key={label}
                        className={
                          label === 'Actions'
                            ? 'processing-actions-heading'
                            : label === 'Outputs'
                              ? `processing-centered-heading${view === 'history' ? ' processing-history-outputs-heading' : ''}`
                              : undefined
                        }
                        title={label === 'Ready in' ? 'Estimated time remaining' : undefined}
                      >
                        {label}
                      </SortableHeader>
                    ),
                  )}
                </tr>
              </thead>
              <tbody ref={tbody}>
                {sorted.map((job) => (
                  <tr key={job.id} data-job-id={job.id}>
                    {selectable && (
                      <td className="bag-select-cell">
                        <Checkbox
                          data-job-select=""
                          aria-label={`Select ${job.name}`}
                          checked={selection.has(job.id)}
                          onChange={(event) => select(job.id, event.target.checked)}
                        />
                      </td>
                    )}
                    <th scope="row">
                      <span className="bag-name" title={job.name}>
                        {job.name}
                      </span>
                    </th>
                    {view === 'queue' ? (
                      <>
                        <td className="bag-recorded">
                          <JobTime timestamp={job.queuedAt} />
                        </td>
                        <td className="bag-recorded">
                          <span data-ready-in="">
                            {job.readyIn === null
                              ? 'Unavailable'
                              : formatReadyIn(job.readyIn ?? readyIn.get(job.id)!)}
                          </span>
                        </td>
                        <td className="bag-number processing-centered-cell">{job.outputs}</td>
                        <td>
                          <div className="processing-row-actions">
                            {actionButton(job, 'cancel', 'Cancel', job.canCancel === false)}
                          </div>
                        </td>
                      </>
                    ) : view === 'failures' ? (
                      <>
                        <td className="bag-number">
                          {job.failures!.length} of {job.outputs}
                        </td>
                        <td>
                          <button
                            type="button"
                            className="processing-failure-summary"
                            data-failure-details=""
                            aria-label={`View full error details for ${job.name}, ${job.failures!.length} ${job.failures!.length === 1 ? 'error' : 'errors'}`}
                            aria-haspopup="dialog"
                            title={job.failures![0].code}
                            onClick={() => setFailure(job)}
                          >
                            <code className="processing-error-code">
                              {job.failures![0].code.split(':')[0]}
                            </code>
                            {job.failures!.length > 1 && (
                              <span className="failure-more">+{job.failures!.length - 1}</span>
                            )}
                          </button>
                        </td>
                        <td>
                          <div className="processing-row-actions">
                            {actionButton(job, 'retry', 'Retry')}
                          </div>
                        </td>
                      </>
                    ) : (
                      <>
                        <td className="bag-recorded">
                          <JobTime timestamp={job.completedAt!} />
                        </td>
                        <td className="bag-number">
                          {job.runtimeKnown === false ? '—' : formatDuration(job.duration)}
                        </td>
                        <td className="bag-number">{job.size}</td>
                        <td className="bag-number processing-centered-cell">
                          <span className="processing-history-outputs">{job.outputs}</span>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </TableBody>
          {more?.[view === 'queue' ? 'queued' : view === 'failures' ? 'failed' : 'history'] && (
            <button
              className="load-more"
              type="button"
              disabled={busy}
              onClick={() =>
                void service.loadMore?.(
                  view === 'queue' ? 'queued' : view === 'failures' ? 'failed' : 'history',
                )
              }
            >
              Load more
            </button>
          )}
          <span className="sr-only" data-processing-notice="" role="status">
            {notice}
          </span>
        </TablePanel>
        <Dialog
          open={!!failure}
          onClose={() => setFailure(null)}
          labelledBy="failure-details-title"
          className="processing-failure-dialog"
        >
          <header>
            <h2 id="failure-details-title">Failed outputs</h2>
            <span data-failure-total="">
              {failure?.failures?.length} of {failure?.outputs}
            </span>
          </header>
          <p className="failure-job-name">{failure?.name}</p>
          <ol className="processing-failure-list">
            {failure?.failures?.map((item, index) => (
              <li key={index}>
                <strong>{item.output}</strong>
                <code className="processing-error-code">{item.code}</code>
              </li>
            ))}
          </ol>
          <footer>
            <button type="submit">Done</button>
          </footer>
        </Dialog>
        <Dialog
          open={!!cancel}
          onClose={() => setCancel(null)}
          labelledBy="cancel-job-title"
          describedBy="cancel-job-description"
          className="processing-confirm-dialog"
          initialFocus="[data-keep-job]"
          onSubmit={async () => {
            if (!cancel) return;
            if (cancel.active) {
              if ((await service.cancelProcessing()) === false) return;
              queueMicrotask(() => queueTab.current?.focus({ preventScroll: true }));
            } else {
              if ((await service.cancelJobs(cancel.ids)) === false) return;
              setSelection((current) => new Set([...current].filter((id) => !cancel.ids.has(id))));
              setNotice(
                `${cancel.ids.size} ${cancel.ids.size === 1 ? 'job cancelled' : 'jobs cancelled'}.`,
              );
              queueMicrotask(() => scroll.current?.focus({ preventScroll: true }));
            }
            setCancel(null);
          }}
        >
          <header>
            <h2 id="cancel-job-title">
              {cancel?.active
                ? 'Cancel processing?'
                : `Cancel ${cancelCount === 1 ? 'queued job' : `${cancelCount} queued jobs`}?`}
            </h2>
          </header>
          <p id="cancel-job-description">
            {cancelCount === 1
              ? 'Are you sure you want to cancel this job?'
              : `Are you sure you want to cancel these ${cancelCount} jobs?`}
          </p>
          <p className="inline-error" role="alert" hidden={!error}>
            {error}
          </p>
          <footer>
            <button type="button" disabled={busy} data-keep-job="" onClick={() => setCancel(null)}>
              {cancel?.active ? 'Keep processing' : 'Keep in queue'}
            </button>
            <button type="submit" className="cancel-confirm" disabled={busy}>
              {cancelCount === 1 ? 'Cancel job' : `Cancel ${cancelCount} jobs`}
            </button>
          </footer>
        </Dialog>
      </div>
    </Page>
  );
}
