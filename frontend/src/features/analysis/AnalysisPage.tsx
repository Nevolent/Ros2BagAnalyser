import { useCallback, useEffect, useRef, useState } from 'react';
import { Page } from '../../components/Page';
import { SidePanel, Workspace } from '../../components/Workspace';
import { useRememberedState, useWorkspace, useWorkspaceService } from '../../app/WorkspaceProvider';
import { useRecordingId } from '../../app/useRoute';
import type { AnalysisRecording } from '../../data/types';
import { RecordingDetails } from './RecordingDetails';
import { Timeline } from './Timeline';
import { stopCamera } from './camera-clock';
function Camera({
  camera,
  onError,
}: {
  camera: AnalysisRecording['cameras'][number];
  onError(id: string, message: string): void;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const retry = useRef<() => void>(() => {});
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    const element = video.current;
    if (!element) return;
    let attempts = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const clearFailure = () => {
      setFailed(false);
      element.dataset.failed = 'false';
      onError(camera.id, '');
    };
    const reload = () => {
      clearTimeout(timer);
      timer = undefined;
      clearFailure();
      stopCamera(element);
      element.load();
    };
    const recover = () => {
      if (timer !== undefined) return;
      if (attempts < 3) {
        // A freshly published file or interrupted range request may need another read.
        timer = setTimeout(reload, [500, 1500, 3000][attempts++]);
      } else {
        element.dataset.failed = 'true';
        setFailed(true);
        onError(camera.id, `${camera.label} camera could not be loaded. Retry the camera.`);
      }
    };
    const ready = () => {
      clearTimeout(timer);
      timer = undefined;
      clearFailure();
    };
    retry.current = () => {
      attempts = 0;
      reload();
    };
    element.addEventListener('error', recover);
    element.addEventListener('loadeddata', ready);
    if (element.error) recover();
    return () => {
      clearTimeout(timer);
      element.removeEventListener('error', recover);
      element.removeEventListener('loadeddata', ready);
    };
  }, [camera.id, camera.label, camera.src, onError]);
  return (
    <section className={`analysis-camera analysis-camera-${camera.id}`} aria-label={camera.region}>
      {camera.media ? (
        <>
          {camera.src && (
            <video
              ref={video}
              src={camera.src}
              muted
              playsInline
              preload="auto"
              data-coverage-start={camera.start}
              data-coverage-end={camera.end}
              aria-label={camera.alt}
            />
          )}
          <p className="camera-state" data-camera-state="" role="status">
            {failed
              ? 'Camera could not be loaded.'
              : camera.src
                ? 'Loading camera…'
                : camera.message}
          </p>
          {failed && (
            <button className="camera-retry" type="button" onClick={() => retry.current()}>
              Retry {camera.label.toLowerCase()} camera
            </button>
          )}
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
  const [mediaErrors, setMediaErrors] = useState<Record<string, string>>({});
  const onError = useCallback(
    (id: string, message: string) =>
      setMediaErrors((errors) => (errors[id] === message ? errors : { ...errors, [id]: message })),
    [],
  );
  useEffect(() => {
    setMediaErrors({});
    if (id) return service.loadAnalysis?.(id);
  }, [service, id]);
  const recording = service.analysis;
  useEffect(() => setMediaErrors({}), [recording?.bundle.mediaVersion]);
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
                  ...Object.values(mediaErrors).filter(Boolean),
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
