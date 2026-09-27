import { useEffect, useRef, useState } from 'react';
import type { ActiveJob } from '../../data/types';
import { Icon } from '../../components/Icon';
import { formatDuration } from '../../lib/format';
export function ActiveJobCard({
  active,
  onCancel,
  busy,
}: {
  active: ActiveJob;
  busy?: boolean;
  onCancel(): void;
}) {
  const frozen = active.paused || active.pendingPause || active.cancelled || active.idle;
  const [clockSeconds, setClockSeconds] = useState(active.elapsed);
  const clock = useRef({ id: active.id, seconds: active.elapsed, at: performance.now(), frozen });
  useEffect(() => {
    const now = performance.now();
    const previous = clock.current;
    if (previous.id !== active.id || previous.frozen !== frozen) {
      const seconds =
        frozen && previous.id === active.id && !previous.frozen
          ? previous.seconds + (now - previous.at) / 1000
          : active.elapsed;
      clock.current = { id: active.id, seconds, at: now, frozen };
      setClockSeconds(seconds);
    } else if (!frozen) {
      const seconds = Math.max(active.elapsed, previous.seconds + (now - previous.at) / 1000);
      clock.current = { id: active.id, seconds, at: now, frozen };
      setClockSeconds(seconds);
    }
  }, [active.id, active.elapsed, frozen]);
  useEffect(() => {
    if (!active.live) return;
    const timer = window.setInterval(() => {
      const anchor = clock.current;
      if (!anchor.frozen) setClockSeconds(anchor.seconds + (performance.now() - anchor.at) / 1000);
    }, 200);
    return () => window.clearInterval(timer);
  }, [active.live]);
  const elapsed = active.live ? clockSeconds : active.elapsed;
  const estimated = active.duration > 0 && active.estimateStatus !== 'unavailable';
  const exceeded =
    estimated && (elapsed >= active.duration || active.estimateStatus === 'exceeded');
  const percent = estimated
    ? Math.min(99, Math.max(0, Math.floor((elapsed / active.duration) * 100)))
    : 0;
  if (active.idle || active.cancelled) return null;
  return (
    <section
      className={`processing-job${active.paused || active.pendingPause || active.cancelled ? ' is-paused' : ''}${active.cancelled ? ' is-cancelled' : ''}`}
      aria-label="Active processing job"
    >
      <div className="processing-job-heading">
        <div>
          <h2>{active.name}</h2>
          <p data-processing-status="" aria-live="polite">
            {active.live ? active.status : active.cancelled ? 'Cancelled' : ''}
          </p>
        </div>
        <div className="processing-actions">
          <button
            type="button"
            data-processing-cancel=""
            aria-label="Cancel processing"
            title="Cancel processing"
            hidden={active.idle}
            disabled={
              busy || active.cancelled || (active.live && !active.controls?.includes('cancel'))
            }
            onClick={onCancel}
          >
            <Icon name="cancel" strokeWidth={1.75} strokeLinejoin={undefined} />
          </button>
        </div>
      </div>
      <div
        className={`processing-progress${active.elapsed === 0 ? ' is-resetting' : ''}`}
        role="progressbar"
        aria-label="Estimated processing progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={estimated ? percent : undefined}
        aria-valuetext={
          exceeded
            ? 'Estimate exceeded'
            : estimated
              ? `${percent}% of estimated time`
              : 'Estimate unavailable'
        }
      >
        <span style={{ width: `${percent}%` }} />
      </div>
      <div className="processing-timing" hidden={active.idle}>
        <span>
          Elapsed <strong data-processing-elapsed="">{formatDuration(elapsed)}</strong>
        </span>
        <span>
          Estimated{' '}
          <strong>
            {active.live && active.estimateStatus === 'unavailable'
              ? 'Unavailable'
              : formatDuration(active.duration)}
          </strong>
        </span>
        <span data-processing-percent="">
          {exceeded ? 'Estimate exceeded' : estimated ? `${percent}%` : 'Estimate unavailable'}
        </span>
      </div>
    </section>
  );
}
