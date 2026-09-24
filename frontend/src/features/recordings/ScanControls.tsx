import { useEffect, useRef, useState } from 'react';
import { useWorkspace, useWorkspaceService } from '../../app/WorkspaceProvider';
import { Button } from '../../components/Button';
import { Icon } from '../../components/Icon';
import { formatDateTime } from '../../lib/format';
import { Popover } from '../../components/Popover';
export function ScanControls() {
  const [demoScanning, setScanning] = useState(false);
  const [demoLastScan, setLastScan] = useState<Date | null>(null);
  const service = useWorkspaceService();
  const snapshot = useWorkspace();
  const scanning = service.rescan ? snapshot.scanning : demoScanning;
  const lastScan = service.rescan
    ? snapshot.lastScan
      ? new Date(snapshot.lastScan)
      : null
    : demoLastScan;
  const [history, setHistory] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!demoScanning) return;
    const timer = setTimeout(() => {
      setScanning(false);
      setLastScan(new Date());
    }, 5000);
    return () => clearTimeout(timer);
  }, [demoScanning]);
  function close(restore = false) {
    setHistory(false);
    if (restore) trigger.current?.focus();
  }
  return (
    <div
      className="recordings-rescan cn-button-group flex w-fit items-stretch [&>*]:focus-visible:relative [&>*]:focus-visible:z-10 [&>[data-slot=select-trigger]:not([class*='w-'])]:w-fit [&>input]:flex-1 cn-button-group-orientation-horizontal [&>*:not(:first-child)]:rounded-l-none [&>*:not(:first-child)]:border-l-0 [&>*:not(:last-child)]:rounded-r-none"
      data-slot="button-group"
      role="group"
    >
      <Button
        data-rescan-archive=""
        disabled={scanning || snapshot.busy}
        aria-busy={scanning || undefined}
        className={scanning ? 'rescan-active' : ''}
        onClick={() => (service.rescan ? void service.rescan() : setScanning(true))}
      >
        <span>{scanning ? 'Scanning archive' : 'Rescan Archive'}</span>
      </Button>
      <div
        data-orientation="vertical"
        role="none"
        className="shrink-0 bg-border data-[orientation=horizontal]:h-px data-[orientation=vertical]:w-px data-[orientation=vertical]:self-stretch cn-button-group-separator relative self-stretch data-[orientation=horizontal]:mx-px data-[orientation=vertical]:my-px data-[orientation=vertical]:h-auto data-[orientation=horizontal]:w-auto"
        data-slot="button-group-separator"
      />
      <Button
        ref={trigger}
        size="icon"
        aria-label="Archive scan history"
        id="archive-scan-history-trigger"
        data-scan-history=""
        aria-controls="archive-scan-history"
        aria-haspopup="dialog"
        aria-expanded={history}
        data-state={history ? 'open' : 'closed'}
        onClick={() => setHistory(!history)}
      >
        <Icon
          name="chevron"
          strokeWidth={2}
          className="lucide lucide-chevron-down"
          width="24"
          height="24"
        />
      </Button>
      {history && (
        <Popover
          anchor={trigger}
          onClose={close}
          align="right"
          className="archive-scan-history"
          id="archive-scan-history"
          role="dialog"
          aria-label="Scan history"
        >
          <dl>
            <dt>Last scan completed</dt>
            <dd data-last-scan-completed="">
              {lastScan ? (
                <time dateTime={lastScan.toISOString()}>{formatDateTime(lastScan)}</time>
              ) : (
                'Not scanned yet'
              )}
            </dd>
          </dl>
        </Popover>
      )}
    </div>
  );
}
