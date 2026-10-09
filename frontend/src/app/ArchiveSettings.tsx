import { useEffect, useRef, useState } from 'react';
import { useWorkspace, useWorkspaceService } from './WorkspaceProvider';
import { Icon } from '../components/Icon';
import { Popover } from '../components/Popover';

export function ArchiveSettings() {
  const service = useWorkspaceService();
  const snapshot = useWorkspace();
  const [open, setOpen] = useState(false);
  const [demoScanning, setDemoScanning] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const scanning = service.rescan ? snapshot.scanning : demoScanning;
  function close(restore = false) {
    setOpen(false);
    if (restore) trigger.current?.focus();
  }
  useEffect(() => {
    if (!demoScanning) return;
    const timer = setTimeout(() => {
      setDemoScanning(false);
      setOpen(false);
      trigger.current?.focus();
    }, 5000);
    return () => clearTimeout(timer);
  }, [demoScanning]);
  async function rescan() {
    if (!service.rescan) {
      setDemoScanning(true);
      return;
    }
    if (await service.rescan()) close(true);
  }
  return (
    <div className="sidebar-settings" data-slot="sidebar-footer">
      <button
        ref={trigger}
        type="button"
        className="sidebar-settings-trigger"
        aria-label="Settings"
        aria-controls="archive-settings"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-busy={scanning || undefined}
        data-rail-link=""
        onClick={() => setOpen(!open)}
      >
        <Icon name="settings" />
      </button>
      {open && (
        <Popover
          anchor={trigger}
          onClose={close}
          side="right"
          className="archive-settings"
          id="archive-settings"
          role="dialog"
          aria-label="Settings"
        >
          <button
            type="button"
            data-autofocus=""
            disabled={scanning || snapshot.busy}
            aria-busy={scanning || undefined}
            onClick={() => void rescan()}
          >
            {scanning ? 'Rescanning…' : 'Do a full rescan'}
          </button>
        </Popover>
      )}
    </div>
  );
}
