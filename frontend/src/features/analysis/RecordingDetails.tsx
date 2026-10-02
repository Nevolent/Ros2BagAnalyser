import { useState } from 'react';
import { Tabs } from '../../components/Tabs';
import { SearchField } from '../../components/SearchField';
import { StatusDiagnostic } from '../recordings/StatusDiagnostic';
import { conciseIssues } from '../../data/diagnostics';
import { ScrollArea } from '../../components/ScrollArea';
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
                  : ['Queued', 'Processing', 'Not planned', 'Unavailable', 'Missing'].includes(
                        asset.status,
                      )
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
  const [tab, setTab] = useState<'details' | 'topics'>('details');
  const [query, setQuery] = useState('');
  const topics = recording.topics?.filter((topic) =>
    (topic.name + ' ' + topic.message_type).toLowerCase().includes(query.trim().toLowerCase()),
  );
  const errors = conciseIssues(recording.errors ?? []);
  const at = (ns: string) => {
    const seconds = Number(BigInt(ns)) / 1e9;
    return `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(1).padStart(4, '0')}`;
  };
  return (
    <div className="recording-details-panel">
      <Tabs<'details' | 'topics'>
        label="Recording information view"
        items={[
          { value: 'details', label: 'Details' },
          { value: 'topics', label: 'Topics', count: recording.topics?.length },
        ]}
        value={tab}
        onChange={setTab}
        controls="recording-panel-content"
      />
      {tab === 'topics' ? (
        <div id="recording-panel-content" className="recording-topics">
          <SearchField
            aria-label="Search topics"
            placeholder="Search topics or types"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <ScrollArea label="Recording topics" viewportClassName="recording-topics-list">
            {topics == null ? (
              <p className="recording-muted-state">Rescan to load topic names.</p>
            ) : !topics.length ? (
              <p className="recording-muted-state">
                {query ? 'No matching topics.' : 'No topics recorded.'}
              </p>
            ) : (
              <ul>
                {topics.map((topic, index) => (
                  <li key={`${topic.name}-${index}`}>
                    <code>{topic.name}</code>
                    <span>{topic.message_type}</span>
                    <span>
                      {BigInt(topic.message_count).toLocaleString()} messages ·{' '}
                      {topic.serialization_format}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </ScrollArea>
        </div>
      ) : (
        <div id="recording-panel-content" className="recording-details-content">
          <ScrollArea
            viewportClassName="recording-details-body"
            label="Recording information and assets"
          >
            <div>
              <section className="recording-overview" aria-label="Recording information">
                <dl className="recording-info">
                  {recording.info.map((field) => (
                    <div key={field.label}>
                      <dt>{field.label}</dt>
                      <dd>
                        {field.kind === 'status' && recording.healthIssues?.length ? (
                          <StatusDiagnostic status={field.value} issues={recording.healthIssues} />
                        ) : (
                          <Value field={field} />
                        )}
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
              <section className="recording-assets-group" aria-label="Timestamp inspection">
                <h3>Timestamp gaps</h3>
                {!recording.timing ? (
                  <p className="recording-muted-state">Rescan to check timestamps.</p>
                ) : (
                  <>
                    {recording.timing.status === 'partial' && (
                      <p className="recording-muted-state">
                        Partial check · inspection limit reached.
                      </p>
                    )}
                    {!recording.timing.gaps.length ? (
                      <p className="recording-muted-state">
                        {recording.timing.status === 'complete'
                          ? 'No large gaps detected.'
                          : 'No large gaps found in the checked portion.'}
                      </p>
                    ) : (
                      <ul className="recording-gap-list">
                        {recording.timing.gaps.map((gap, index) => (
                          <li key={index}>
                            <strong>
                              {(Number(BigInt(gap.duration_ns)) / 1e9).toFixed(1)} s gap
                            </strong>
                            <span>
                              {at(gap.start_ns)}–{at(gap.end_ns)}
                            </span>
                            <code>{gap.topic ?? 'All recorded messages'}</code>
                          </li>
                        ))}
                      </ul>
                    )}
                  </>
                )}
              </section>
              {!!errors.length && (
                <section className="recording-errors" aria-label="Recording errors">
                  {errors.map((error) => (
                    <p key={error}>{error}</p>
                  ))}
                </section>
              )}
            </div>
          </ScrollArea>
        </div>
      )}
    </div>
  );
}
