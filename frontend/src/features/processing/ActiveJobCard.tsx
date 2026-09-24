import type { ActiveJob } from '../../data/types';
import { Icon } from '../../components/Icon';
import { formatDuration } from '../../lib/format';
export function ActiveJobCard({
  active,
  onToggle,
  onCancel,
}: {
  active: ActiveJob;
  onToggle(): void;
  onCancel(): void;
}) {
  const percent =
    active.elapsed >= active.duration
      ? 100
      : Math.min(99, Math.round((active.elapsed / active.duration) * 100));
  return (
    <section
      className={`processing-job${active.paused || active.cancelled ? ' is-paused' : ''}${active.cancelled ? ' is-cancelled' : ''}`}
      aria-label="Active processing job"
    >
      <div className="processing-job-heading">
        <div>
          <h2>{active.name}</h2>
          <p data-processing-status="" aria-live="polite">
            {active.cancelled ? 'Cancelled' : ''}
          </p>
        </div>
        <div className="processing-actions">
          <button
            type="button"
            data-processing-pause=""
            aria-label={active.paused ? 'Resume processing' : 'Pause processing'}
            title={active.paused ? 'Resume processing' : 'Pause processing'}
            hidden={active.cancelled}
            onClick={onToggle}
          >
            <Icon
              name={active.paused ? 'play' : 'pause'}
              strokeWidth={1.75}
              strokeLinejoin={undefined}
            />
          </button>
          <button
            type="button"
            data-processing-cancel=""
            aria-label="Cancel processing"
            title="Cancel processing"
            disabled={active.cancelled}
            onClick={onCancel}
          >
            <Icon name="cancel" strokeWidth={1.75} strokeLinejoin={undefined} />
          </button>
        </div>
      </div>
      <div
        className={`processing-progress${active.elapsed === 0 ? ' is-resetting' : ''}`}
        role="progressbar"
        aria-label="Luna testing progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
        aria-valuetext={`${percent}%${active.cancelled ? ', cancelled' : active.paused ? ', paused' : ''}`}
      >
        <span style={{ width: `${percent}%` }} />
      </div>
      <div className="processing-timing">
        <span>
          Elapsed <strong data-processing-elapsed="">{formatDuration(active.elapsed)}</strong>
        </span>
        <span>
          Estimated <strong>{formatDuration(active.duration)}</strong>
        </span>
        <span data-processing-percent="">{`${percent}%`}</span>
      </div>
    </section>
  );
}
