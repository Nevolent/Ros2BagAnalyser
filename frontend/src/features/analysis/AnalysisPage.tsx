import { useCallback, useEffect, useRef, useState } from 'react';
import { Page } from '../../components/Page';
import { SidePanel, Workspace } from '../../components/Workspace';
import { useRememberedState, useWorkspace, useWorkspaceService } from '../../app/WorkspaceProvider';
import { useRecordingId } from '../../app/useRoute';
import type { AnalysisRecording } from '../../data/types';
import { RecordingDetails } from './RecordingDetails';
import { Timeline } from './Timeline';
function Camera({
  camera,
  onError,
}: {
  camera: AnalysisRecording['cameras'][number];
  onError(message: string): void;
}) {
  return (
    <section className={`analysis-camera analysis-camera-${camera.id}`} aria-label={camera.region}>
      {camera.media ? (
        <>
          {camera.src && (
            <video
              key={camera.src}
              src={camera.src}
              muted
              playsInline
              preload="auto"
              data-coverage-start={camera.start}
              data-coverage-end={camera.end}
              aria-label={camera.alt}
              onError={() => onError(`${camera.label} camera could not be loaded.`)}
            />
          )}
          <p className="camera-state" data-camera-state="" role="status">
            {camera.src ? 'Loading camera…' : camera.message}
          </p>
        </>
      ) : (
        <img src={camera.src} alt={camera.alt} />
      )}
      <div className="camera-caption">
        <span>{camera.label}</span>
      </div>
    </section>
  );
}
export function AnalysisPage() {
  const service = useWorkspaceService();
  const { analysisLoading, analysisError } = useWorkspace();
  const routeId = useRecordingId();
  const [lastId, setLastId] = useRememberedState('analysis.lastId', '');
  const id = routeId || lastId || service.analysis?.id || '';
  useEffect(() => {
    if (routeId) setLastId(routeId);
  }, [routeId, setLastId]);
  const [mediaErrors, setMediaErrors] = useState<string[]>([]);
  const onError = useCallback(
    (message: string) =>
      setMediaErrors((errors) => (errors.includes(message) ? errors : [...errors, message])),
    [],
  );
  useEffect(() => {
    setMediaErrors([]);
    if (id) return service.loadAnalysis?.(id);
  }, [service, id]);
  const recording = service.analysis;
  useEffect(() => setMediaErrors([]), [recording?.bundle.mediaVersion]);
  const root = useRef<HTMLDivElement>(null);
  const hasRecording = recording && (!service.loadAnalysis || recording.id === id);
  return (
    <Page
      name="analysis"
      title="Analysis"
      breadcrumb={
        hasRecording ? (
          <>
            <span className="analysis-breadcrumb-separator" aria-hidden="true">
              /
            </span>
            <span className="analysis-recording-name" title={recording.name}>
              {recording.name}
            </span>
          </>
        ) : undefined
      }
    >
      {hasRecording ? (
        <Workspace name="analysis" side="right" panelLabel="recording details" rootRef={root}>
          <div className="analysis-cameras">
            {recording.cameras.map((camera) => (
              <Camera key={`${id}-${camera.id}-${camera.src}`} camera={camera} onError={onError} />
            ))}
          </div>
          <SidePanel title="Recording details">
            <RecordingDetails
              recording={{
                ...recording,
                errors: [
                  ...(recording.errors ?? []),
                  ...mediaErrors,
                  ...(analysisError ? [analysisError] : []),
                ],
              }}
            />
          </SidePanel>
          <Timeline
            key={recording.id ?? recording.name}
            recordingKey={recording.id ?? recording.name}
            bundle={recording.bundle}
            workspaceRef={root}
          />
        </Workspace>
      ) : (
        <div
          className={`page-state${analysisError ? ' inline-error' : ''}`}
          role={analysisError ? 'alert' : 'status'}
        >
          {!id && service.loadAnalysis
            ? 'Select a recording from Recordings.'
            : analysisError ||
              (analysisLoading || id
                ? 'Loading recording…'
                : 'Select a recording from Recordings.')}
        </div>
      )}
    </Page>
  );
}
