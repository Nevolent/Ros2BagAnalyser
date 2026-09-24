import { StatusBadge } from '../../components/StatusBadge';
import { useCallback, useMemo, useState } from 'react';
import { useWorkspace, useWorkspaceService } from '../../app/WorkspaceProvider';
import { createFolderIndex } from '../../lib/folder-index';
import { Page } from '../../components/Page';
import { Button } from '../../components/Button';
import { Checkbox } from '../../components/Checkbox';
import { Dialog } from '../../components/Dialog';
import { EmptyState, TableBody, TablePanel } from '../../components/DataTable';
import { FilterMenu } from '../../components/FilterMenu';
import { SearchField } from '../../components/SearchField';
import { Notice } from '../../components/Notice';
import { Workspace } from '../../components/Workspace';
import { FolderBrowser } from './FolderBrowser';
import { ScanControls } from './ScanControls';
import { SortableHeader } from '../../components/SortableHeader';
import { useTableSort, durationInSeconds, sizeInBytes } from '../../lib/useTableSort';
import { formatDateTime } from '../../lib/format';
import type { Recording, RecordingStatus } from '../../data/types';

const recordingSort = {
  name: (item: Recording) => item.name,
  recorded: (item: Recording) => Date.parse(item.recordedAt),
  duration: (item: Recording) => durationInSeconds(item.duration),
  size: (item: Recording) => sizeInBytes(item.size),
  health: (item: Recording) => item.health,
  analysis: (item: Recording) => item.analysis,
};
function Status({ status }: { status: RecordingStatus | Recording['health'] }) {
  return (
    <StatusBadge
      tone={
        status === 'Ready' || status === 'Readable'
          ? 'success'
          : status === 'Failed' || status === 'Damaged'
            ? 'error'
            : 'muted'
      }
    >
      {status}
    </StatusBadge>
  );
}
export function RecordingsPage() {
  const { recordings } = useWorkspace();
  const service = useWorkspaceService();
  const { sorted, sort, toggle } = useTableSort(recordings, recordingSort);
  const folders = service.folders;
  const folderIndex = useMemo(() => createFolderIndex(folders), [folders]);
  const [folder, setFolder] = useState('');
  const [search, setSearch] = useState('');
  const [health, setHealth] = useState('');
  const [analysis, setAnalysis] = useState('');
  const [selection, setSelection] = useState(new Set<string>());
  const [prepare, setPrepare] = useState(false);
  const [goToProcessing, setGoToProcessing] = useState(false);
  const [notice, setNotice] = useState('');
  const dismissNotice = useCallback(() => setNotice(''), []);
  const visible = useMemo(() => {
    const query = search.trim().toLowerCase();
    return new Set(
      recordings
        .filter(
          (recording) =>
            folderIndex.contains(folder, recording.folderId) &&
            (!health || recording.health === health) &&
            (!analysis || recording.analysis === analysis) &&
            `${recording.name} ${formatDateTime(recording.recordedAt)} ${recording.duration} ${recording.size} ${recording.health} ${recording.analysis}`
              .toLowerCase()
              .includes(query),
        )
        .map((recording) => recording.id),
    );
  }, [recordings, folder, search, health, analysis, folderIndex]);
  const selected = recordings.filter((recording) => selection.has(recording.id));
  const visibleSelected = [...visible].filter((id) => selection.has(id)).length;
  const folderLabel = folderIndex.index.get(folder)?.path ?? 'Recordings';
  const filtered = !!(search.trim() || health || analysis);
  function select(id: string, checked: boolean) {
    setSelection((current) => {
      const next = new Set(current);
      checked ? next.add(id) : next.delete(id);
      return next;
    });
  }
  return (
    <Page
      name="recordings"
      title="Recordings"
      actions={
        <div className="recordings-actions">
          <ScanControls />
          <Button
            className="prepare-selected"
            data-prepare-selected=""
            hidden={!selected.length}
            onClick={() => setPrepare(true)}
          >
            Prepare Selected
          </Button>
        </div>
      }
    >
      <Workspace name="recordings">
        <FolderBrowser
          folders={folders}
          recordings={recordings}
          selected={folder}
          onSelect={setFolder}
        />
        <TablePanel
          className="group/card flex flex-col bg-secondary shadow-none ring-0 dark:bg-secondary/50"
          data-size="default"
          data-slot="card"
          data-component="recordings-table"
          aria-label="ROS bag archive"
        >
          <div className="cn-card-header bag-panel-header" data-slot="card-header">
            <span data-folder-label="" title={folderLabel}>
              {folderLabel}
            </span>
          </div>
          <div className="bag-toolbar recordings-toolbar">
            <SearchField
              className="bag-search-field"
              inputClassName="bag-search"
              aria-label="Search recordings"
              placeholder="Search recordings"
              data-bag-search=""
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
            <FilterMenu
              name="health"
              label="Health"
              options={['Readable', 'Damaged']}
              value={health}
              onChange={setHealth}
            />
            <FilterMenu
              name="analysis"
              label="Analysis"
              options={['Ready', 'Not planned', 'Failed', 'Queued']}
              value={analysis}
              onChange={setAnalysis}
            />
          </div>
          <TableBody
            className="recordings-table-body"
            label="ROS bags"
            cardContent
            empty={
              <EmptyState data-bag-empty="" hidden={visible.size > 0}>
                <p>
                  {filtered ? 'No recordings match your filters.' : 'No recordings in this folder.'}
                </p>
                <span>
                  {filtered
                    ? 'Try another search or clear your filters.'
                    : 'Select another folder.'}
                </span>
              </EmptyState>
            }
          >
            <table className="bag-table">
              <caption className="sr-only">
                ROS bags with recording time, duration in minutes, seconds and milliseconds, file
                size, health and analysis status.
              </caption>
              <colgroup>
                <col className="bag-select-column" />
                <col />
                <col className="bag-recorded-column" />
                <col className="bag-duration-column" />
                <col className="bag-size-column" />
                <col className="bag-health-column" />
                <col className="bag-analysis-column" />
              </colgroup>
              <thead>
                <tr>
                  <th scope="col" className="bag-select-cell">
                    <Checkbox
                      data-bag-select-all=""
                      aria-label="Select all visible bags"
                      checked={visible.size > 0 && visibleSelected === visible.size}
                      indeterminate={visibleSelected > 0 && visibleSelected < visible.size}
                      disabled={!visible.size}
                      onChange={(event) => {
                        const checked = event.target.checked;
                        setSelection((current) => {
                          const next = new Set(current);
                          visible.forEach((id) => (checked ? next.add(id) : next.delete(id)));
                          return next;
                        });
                      }}
                    />
                  </th>
                  <SortableHeader column="name" sort={sort} onSort={toggle}>
                    Name
                  </SortableHeader>
                  <SortableHeader column="recorded" sort={sort} onSort={toggle}>
                    Recorded
                  </SortableHeader>
                  <SortableHeader
                    column="duration"
                    sort={sort}
                    onSort={toggle}
                    className="bag-number"
                    title="Minutes:seconds.milliseconds"
                  >
                    Duration
                  </SortableHeader>
                  <SortableHeader column="size" sort={sort} onSort={toggle} className="bag-number">
                    Size
                  </SortableHeader>
                  <SortableHeader
                    column="health"
                    sort={sort}
                    onSort={toggle}
                    className="bag-health-cell"
                  >
                    Health
                  </SortableHeader>
                  <SortableHeader column="analysis" sort={sort} onSort={toggle}>
                    Analysis
                  </SortableHeader>
                </tr>
              </thead>
              <tbody>
                {sorted.map((recording) => (
                  <tr
                    key={recording.id}
                    data-folder-id={recording.folderId}
                    hidden={!visible.has(recording.id)}
                  >
                    <td className="bag-select-cell">
                      <Checkbox
                        aria-label={`Select ${recording.name}`}
                        checked={selection.has(recording.id)}
                        onChange={(event) => select(recording.id, event.target.checked)}
                      />
                    </td>
                    <th scope="row">
                      <span className="bag-name" title={recording.name}>
                        {recording.name}
                      </span>
                    </th>
                    <td className="bag-recorded">
                      <time dateTime={recording.recordedAt}>
                        {formatDateTime(recording.recordedAt)}
                      </time>
                    </td>
                    <td className="bag-number">{recording.duration}</td>
                    <td className="bag-number">{recording.size}</td>
                    <td className="bag-health-cell">
                      <Status status={recording.health} />
                    </td>
                    <td>
                      <Status status={recording.analysis} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableBody>
        </TablePanel>
      </Workspace>
      <Dialog
        open={prepare}
        onClose={() => setPrepare(false)}
        labelledBy="prepare-title"
        describedBy="prepare-description"
        initialFocus="[data-prepare-cancel]"
        onSubmit={() => {
          service.prepare(selection);
          setSelection(new Set());
          setPrepare(false);
          if (goToProcessing) location.hash = '/processing';
          else {
            setNotice(
              `${selected.length} ${selected.length === 1 ? 'recording' : 'recordings'} queued.`,
            );
            queueMicrotask(() =>
              document
                .querySelector<HTMLButtonElement>('[data-rescan-archive]')
                ?.focus({ preventScroll: true }),
            );
          }
        }}
      >
        <header>
          <h2 id="prepare-title">Prepare recordings</h2>
          <span data-prepare-count="">
            {selected.length} {selected.length === 1 ? 'bag' : 'bags'}
          </span>
        </header>
        <p id="prepare-description">
          Prepares front and top camera views and an IMU data bundle, where available.
        </p>
        <ul className="prepare-bag-list" aria-label="Selected recordings">
          {selected.map((recording) => (
            <li key={recording.id}>{recording.name}</li>
          ))}
        </ul>
        <label className="prepare-destination">
          <input
            className="bag-checkbox"
            type="checkbox"
            data-go-to-processing=""
            checked={goToProcessing}
            onChange={(event) => setGoToProcessing(event.target.checked)}
          />
          Go to Processing
        </label>
        <footer>
          <button type="button" data-prepare-cancel="" onClick={() => setPrepare(false)}>
            Cancel
          </button>
          <button type="submit" className="prepare-confirm">
            Confirm
          </button>
        </footer>
      </Dialog>
      {notice && <Notice message={notice} onDismiss={dismissNotice} />}
    </Page>
  );
}
