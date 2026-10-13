import { useState } from 'react';
import { outputMessage } from '../../data/analysis-adapter';
import { Tabs } from '../../components/Tabs';
import { SidePanel } from '../../components/Workspace';
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
  const topics = recording.topics;
  const errors = conciseIssues(recording.errors ?? []);
  return (
    <SidePanel
      title="Recording details"
      heading={
        <Tabs<'details' | 'topics'>
          label="Recording information view"
          items={[
            { value: 'details', label: 'Details' },
            { value: 'topics', label: 'Topics' },
          ]}
          value={tab}
          onChange={setTab}
          controls="recording-panel-content"
        />
      }
    >
      <div className="recording-details-panel">
        {tab === 'topics' ? (
          <div id="recording-panel-content" className="recording-topics">
            <ScrollArea label="Recording topics" viewportClassName="recording-topics-list">
              {topics == null ? (
                <p className="recording-muted-state">Rescan to load topic names.</p>
              ) : !topics.length ? (
                <p className="recording-muted-state">No topics recorded.</p>
              ) : (
                <ul>
                  {topics.map((topic, index) => (
                    <li key={`${topic.name}-${index}`}>
                      <code title={topic.name}>{topic.name}</code>
                      <span title={topic.message_type}>{topic.message_type}</span>
                      <span>{BigInt(topic.message_count).toLocaleString()} messages</span>
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
                        <dd
                          title={
                            field.kind === 'time' && field.dateTime
                              ? formatDateTime(field.dateTime)
                              : field.value
                          }
                        >
                          {field.kind === 'status' && recording.healthIssues?.length ? (
                            <StatusDiagnostic
                              status={field.value}
                              issues={recording.healthIssues}
                            />
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
                <section
                  className="recording-assets-group recording-description"
                  aria-label="AI description"
                >
                  {recording.aiDescription ? (
                    <>
                      <p>{recording.aiDescription.description}</p>
                      {recording.aiDescription.bunker && (
                        <div className="recording-description-tags">
                          <span className="recording-description-tag">Bunker</span>
                        </div>
                      )}
                    </>
                  ) : (
                    <p className="recording-muted-state">
                      {recording.descriptionState === 'not_requested' || !recording.descriptionState
                        ? 'AI description not prepared.'
                        : `AI description: ${outputMessage(recording.descriptionState)}`}
                    </p>
                  )}
                </section>
                {!!errors.length && (
                  <section className="recording-errors" aria-label="Recording errors">
                    {errors.map((error) => (
                      <p key={error} title={error}>
                        {error}
                      </p>
                    ))}
                  </section>
                )}
              </div>
            </ScrollArea>
          </div>
        )}
      </div>
    </SidePanel>
  );
}
