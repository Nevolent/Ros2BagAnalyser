import {
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
} from 'react';
import type { Folder, Recording } from '../../data/types';
import { createFolderIndex } from '../../lib/folder-index';
import { SearchField } from '../../components/SearchField';
import { SidePanel } from '../../components/Workspace';
import { Icon } from '../../components/Icon';

export function FolderBrowser({
  folders,
  recordings,
  selected,
  onSelect,
}: {
  folders: Folder[];
  recordings: Recording[];
  selected: string;
  onSelect(id: string): void;
}) {
  const { index, contains } = useMemo(() => createFolderIndex(folders), [folders]);
  const [expanded, setExpanded] = useState(
    new Set(['synthetic-root', 'bunker', 'bunker-tests', 'bunker-2025', 'lunar', 'lunar-navigation', 'calibration']),
  );
  const [search, setSearch] = useState('');
  const [focused, setFocused] = useState('bunker');
  const rows = useRef(new Map<string, HTMLDivElement>());
  const input = useRef<HTMLInputElement>(null);
  const pendingFocus = useRef<string | null>(null);
  const typeahead = useRef({ text: '', time: 0 });
  const query = search.trim().toLowerCase();
  const matched = new Set(
    [...index].filter(([, entry]) => entry.path.toLowerCase().includes(query)).map(([id]) => id),
  );
  const included = new Set(matched);
  for (const id of matched)
    for (let parent = index.get(id)?.parent; parent; parent = index.get(parent)?.parent)
      included.add(parent);
  const counts = useMemo(
    () =>
      new Map(
        [...index.keys()].map((id) => [
          id,
          recordings.filter((recording) => contains(id, recording.folderId)).length,
        ]),
      ),
    [index, recordings],
  );
  const visible: string[] = [];
  function collect(items: Folder[]) {
    for (const folder of items) {
      if (query && !included.has(folder.id)) continue;
      visible.push(folder.id);
      if (folder.children && (query || expanded.has(folder.id))) collect(folder.children);
    }
  }
  collect(folders);
  const focusId = visible.includes(focused) ? focused : visible[0];
  function focus(id?: string) {
    if (!id) return;
    setFocused(id);
    pendingFocus.current = id;
  }
  useLayoutEffect(() => {
    if (!pendingFocus.current) return;
    const row = rows.current.get(pendingFocus.current);
    row?.focus({ preventScroll: true });
    row?.scrollIntoView({ block: 'nearest' });
    pendingFocus.current = null;
  });
  function toggle(id: string) {
    if (!query)
      setExpanded((current) => {
        const next = new Set(current);
        next.has(id) ? next.delete(id) : next.add(id);
        return next;
      });
  }
  function clearSearch() {
    setSearch('');
    setExpanded((current) => {
      const next = new Set(current);
      for (let parent = index.get(selected)?.parent; parent; parent = index.get(parent)?.parent)
        next.add(parent);
      return next;
    });
  }
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    const id = (event.target as HTMLElement).closest<HTMLElement>('[data-folder]')?.dataset.folder;
    if (!id) return;
    const current = visible.indexOf(id),
      entry = index.get(id)!;
    let next: string | undefined;
    switch (event.key) {
      case 'ArrowDown':
        next = visible[Math.min(current + 1, visible.length - 1)];
        break;
      case 'ArrowUp':
        next = visible[Math.max(0, current - 1)];
        break;
      case 'Home':
        next = visible[0];
        break;
      case 'End':
        next = visible.at(-1);
        break;
      case 'ArrowRight':
        if (entry.folder.children) {
          if (!query && !expanded.has(id)) toggle(id);
          else next = visible[current + 1];
        }
        break;
      case 'ArrowLeft':
        if (entry.folder.children && expanded.has(id) && !query) toggle(id);
        else next = entry.parent;
        break;
      case 'Enter':
      case ' ':
        onSelect(id);
        break;
      default: {
        if (event.key.length !== 1) return;
        const now = Date.now();
        typeahead.current = {
          text:
            now - typeahead.current.time < 600
              ? typeahead.current.text + event.key.toLowerCase()
              : event.key.toLowerCase(),
          time: now,
        };
        next = [...visible.slice(current + 1), ...visible.slice(0, current + 1)].find((key) =>
          index.get(key)!.folder.name.toLowerCase().startsWith(typeahead.current.text),
        );
      }
    }
    event.preventDefault();
    focus(next);
  }
  function branch(items: Folder[]) {
    return items.map((folder, position) => {
      const entry = index.get(folder.id)!,
        open = !!query || expanded.has(folder.id),
        count = counts.get(folder.id) ?? 0;
      return (
        <div
          className="folder-item"
          role="none"
          key={folder.id}
          hidden={!!query && !included.has(folder.id)}
        >
          <div
            ref={(element) => {
              if (element) rows.current.set(folder.id, element);
              else rows.current.delete(folder.id);
            }}
            className={`folder-row${selected !== folder.id && contains(folder.id, selected) ? ' has-selected-descendant' : ''}`}
            data-folder={folder.id}
            role="treeitem"
            aria-label={folder.name}
            aria-level={entry.depth}
            aria-posinset={position + 1}
            aria-setsize={items.length}
            aria-selected={selected === folder.id}
            tabIndex={focusId === folder.id ? 0 : -1}
            title={entry.path}
            style={{ '--folder-depth': entry.depth - 1 } as CSSProperties}
            aria-description={`${count} ${count === 1 ? 'bag' : 'bags'}`}
            aria-expanded={folder.children ? open : undefined}
            aria-owns={folder.children ? `folder-group-${folder.id}` : undefined}
            onClick={() => {
              onSelect(folder.id);
              focus(folder.id);
            }}
            onFocus={() => setFocused(folder.id)}
          >
            {folder.children ? (
              <button
                type="button"
                className="folder-disclosure"
                tabIndex={-1}
                aria-controls={`folder-group-${folder.id}`}
                aria-label={`${open ? 'Collapse' : 'Expand'} ${folder.name}`}
                disabled={!!query}
                onClick={(event) => {
                  event.stopPropagation();
                  toggle(folder.id);
                  focus(folder.id);
                }}
              >
                <svg
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  <path d="m6 4 4 4-4 4" />
                </svg>
              </button>
            ) : (
              <span className="folder-disclosure-space" />
            )}
            <Icon name="folder" className="folder-icon" />
            <span className="folder-name">{folder.name}</span>
            <span className="folder-bag-count" aria-hidden="true">
              {count}
            </span>
          </div>
          {folder.children && (
            <div
              id={`folder-group-${folder.id}`}
              role="group"
              className="folder-children"
              hidden={!open}
            >
              {branch(folder.children)}
            </div>
          )}
        </div>
      );
    });
  }
  return (
    <SidePanel title="Folders" selectedFolder={selected}>
      <div className="folder-search-wrap">
        <SearchField
          inputRef={input}
          className="folder-search-field"
          placeholder="Find a folder…"
          aria-label="Find a folder"
          data-folder-search=""
          autoComplete="off"
          spellCheck={false}
          value={search}
          onChange={(event) => {
            const value = event.target.value;
            if (!value.trim()) clearSearch();
            else setSearch(value);
          }}
          onKeyDown={(event) => {
            if (event.key === 'Escape') {
              event.preventDefault();
              clearSearch();
            }
            if (event.key === 'ArrowDown' || event.key === 'Enter') {
              event.preventDefault();
              focus(visible[0]);
            }
          }}
        />
        <button
          className="folder-clear"
          type="button"
          data-folder-clear=""
          aria-label="Clear folder search"
          title="Clear search"
          hidden={!search}
          onClick={() => {
            clearSearch();
            input.current?.focus();
          }}
        >
          <Icon name="close" strokeLinejoin={undefined} />
        </button>
      </div>
      <nav className="folder-browser" aria-label="Browse folders">
        <div className="folder-list">
          <div role="tree" aria-label="Archive folders" data-folder-tree="" onKeyDown={onKeyDown}>
            {branch(folders)}
          </div>
          <p className="folder-empty" data-folder-empty="" hidden={!query || matched.size > 0}>
            No folders found.
          </p>
        </div>
      </nav>
    </SidePanel>
  );
}
