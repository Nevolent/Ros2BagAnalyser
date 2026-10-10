import { useEffect, useState } from 'react';
import { useWorkspace, useWorkspaceService } from './WorkspaceProvider';
import { Icon } from '../components/Icon';

export function ArchiveSettings() {
  const service = useWorkspaceService();
  const snapshot = useWorkspace();
  const [demoScanning, setDemoScanning] = useState(false);
  const scanning = service.rescan ? snapshot.scanning : demoScanning;
  useEffect(() => {
    if (!demoScanning) return;
    const timer = setTimeout(() => setDemoScanning(false), 5000);
    return () => clearTimeout(timer);
  }, [demoScanning]);
  async function rescan() {
    if (scanning || snapshot.busy) return;
    if (!service.rescan) setDemoScanning(true);
    else await service.rescan();
  }
  return (
    <div className="sidebar-settings" data-slot="sidebar-footer">
      <button
        type="button"
        className="sidebar-settings-trigger"
        aria-label={scanning ? 'Scanning archive' : 'Full rescan'}
        aria-disabled={scanning || snapshot.busy || undefined}
        aria-busy={scanning || undefined}
        data-rail-link=""
        onClick={() => void rescan()}
      >
        <Icon
          name="retry"
          strokeWidth={2}
          className={scanning ? 'archive-rescan-spinning' : undefined}
        />
      </button>
    </div>
  );
}
