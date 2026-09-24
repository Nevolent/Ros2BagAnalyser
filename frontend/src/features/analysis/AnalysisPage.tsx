import { useRef } from 'react';
import { Page } from '../../components/Page';
import { SidePanel, Workspace } from '../../components/Workspace';
import { useWorkspaceService } from '../../app/WorkspaceProvider';
import { RecordingDetails } from './RecordingDetails';
import { Timeline } from './Timeline';
export function AnalysisPage() {
  const recording = useWorkspaceService().analysis;
  const root = useRef<HTMLDivElement>(null);
  return (
    <Page
      name="analysis"
      title="Analysis"
      breadcrumb={
        <>
          <span className="analysis-breadcrumb-separator" aria-hidden="true">
            /
          </span>
          <span className="analysis-recording-name" title={recording.name}>
            {recording.name}
          </span>
        </>
      }
    >
      <Workspace name="analysis" side="right" panelLabel="recording details" rootRef={root}>
        <div className="analysis-cameras">
          {recording.cameras.map((camera) => (
            <section
              key={camera.id}
              className={`analysis-camera analysis-camera-${camera.id}`}
              aria-label={camera.region}
            >
              <img src={camera.src} alt={camera.alt} />
              <div className="camera-caption">
                <span>{camera.label}</span>
              </div>
            </section>
          ))}
        </div>
        <SidePanel title="Recording details">
          <RecordingDetails recording={recording} />
        </SidePanel>
        <Timeline key={recording.name} bundle={recording.bundle} workspaceRef={root} />
      </Workspace>
    </Page>
  );
}
