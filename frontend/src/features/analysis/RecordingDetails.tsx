import type { AnalysisRecording, RecordingAsset } from '../../data/types';
import { formatDateTime } from '../../lib/format';
import { StatusBadge } from '../../components/StatusBadge';

type Field = AnalysisRecording['info'][number];
function Value({ field }: { field: Field }) {
  if (field.kind === 'time')
    return (
      <time dateTime={field.dateTime}>
        {field.dateTime ? formatDateTime(field.dateTime) : field.value}
      </time>
    );
  if (field.kind === 'code') return <code>{field.value}</code>;
  if (field.kind === 'status')
    return (
      <StatusBadge
        tone={field.value === 'Damaged' || field.value === 'Review' ? 'error' : 'success'}
      >
        {field.value}
      </StatusBadge>
    );
  return <>{field.value}</>;
}
function Assets({ items }: { items: RecordingAsset[] }) {
  return (
    <ul className="recording-assets">
      {items.map((asset) => (
        <li key={asset.name}>
          <div className="recording-asset-heading">
            <span title={asset.name}>{asset.name}</span>
            <StatusBadge
              tone={
                asset.status === 'Ready' || asset.status === 'Readable'
                  ? 'success'
                  : ['Queued', 'Processing', 'Not planned'].includes(asset.status)
                    ? 'muted'
                    : 'error'
              }
            >
              {asset.status}
            </StatusBadge>
          </div>
          <div className="recording-asset-meta">
            <span title={asset.format}>{asset.format}</span>
            <span>{asset.size}</span>
          </div>
        </li>
      ))}
    </ul>
  );
}
export function RecordingDetails({ recording }: { recording: AnalysisRecording }) {
  return (
    <div
      className="recording-details-body"
      tabIndex={0}
      role="region"
      aria-label="Recording information and assets"
    >
      <section className="recording-overview" aria-label="Recording information">
        <dl className="recording-info">
          {recording.info.map((field) => (
            <div key={field.label}>
              <dt>{field.label}</dt>
              <dd>
                <Value field={field} />
              </dd>
            </div>
          ))}
        </dl>
      </section>
      <section className="recording-assets-group" aria-label="Analysis outputs">
        <Assets items={recording.outputs} />
      </section>
      <section className="recording-assets-group" aria-label="Source components">
        <Assets items={recording.sources} />
      </section>
      {!!recording.errors?.length && (
        <section className="recording-errors" aria-label="Recording errors">
          {recording.errors.map((error) => (
            <p key={error}>{error}</p>
          ))}
        </section>
      )}
    </div>
  );
}
