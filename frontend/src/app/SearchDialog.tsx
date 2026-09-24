import { useLayoutEffect, useRef, useState, type CSSProperties } from 'react';
import { createPortal } from 'react-dom';
import { useWorkspaceService } from './WorkspaceProvider';
import { searchGroups } from './search-items';
export function SearchDialog({ onClose }: { onClose(): void }) {
  const service = useWorkspaceService();
  const groups = service.observe
    ? [
        {
          ...searchGroups[0],
          items: searchGroups[0].items.filter((item) =>
            ['recordings', 'processing', 'analysis'].includes(item.route),
          ),
        },
      ]
    : searchGroups;
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const items = groups.flatMap((group) => group.items);
  const visible = items.filter((item) =>
    item.label.toLowerCase().includes(query.trim().toLowerCase()),
  );
  const active = visible[selected];
  useLayoutEffect(() => {
    const root = document.getElementById('app')!;
    const restore = document.querySelector<HTMLElement>('[data-rail-logo]');
    root.inert = true;
    document.body.style.overflow = 'hidden';
    input.current?.focus();
    return () => {
      root.inert = false;
      document.body.style.overflow = '';
      restore?.focus({ preventScroll: true });
    };
  }, []);
  function choose(route: string) {
    onClose();
    location.hash = `/${route}`;
  }
  return createPortal(
    <div className="ui-portal">
      <div className="dialog-backdrop" onClick={onClose} />
      <div
        role="dialog"
        aria-label="Search"
        aria-modal="true"
        data-state="open"
        className="cn-dialog-content fixed left-1/2 z-50 w-full -translate-x-1/2 cn-command-dialog top-1/3 translate-y-0 overflow-hidden p-0"
        data-slot="dialog-content"
        tabIndex={-1}
        style={{ pointerEvents: 'auto' }}
        onKeyDown={(event) => {
          if (event.key === 'Escape') {
            event.preventDefault();
            onClose();
          }
          if (event.key === 'Tab') {
            event.preventDefault();
            input.current?.focus();
          }
        }}
      >
        <div
          tabIndex={-1}
          className="cn-command flex size-full flex-col overflow-hidden"
          data-slot="command"
          cmdk-root=""
        >
          <label cmdk-label="" htmlFor="command-search" className="sr-only" />
          <div className="cn-command-input-wrapper" data-slot="command-input-wrapper">
            <div
              className="group/input-group cn-input-group relative flex w-full min-w-0 items-center outline-none has-[>textarea]:h-auto cn-command-input-group"
              data-slot="input-group"
              role="group"
            >
              <input
                ref={input}
                className="cn-command-input outline-hidden disabled:cursor-not-allowed disabled:opacity-50"
                data-slot="command-input"
                placeholder="Search..."
                cmdk-input=""
                autoComplete="off"
                autoCorrect="off"
                spellCheck={false}
                aria-autocomplete="list"
                role="combobox"
                aria-expanded="true"
                aria-controls="command-suggestions"
                aria-label="Search pages"
                aria-activedescendant={active ? `command-${active.route}` : undefined}
                id="command-search"
                type="text"
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setSelected(0);
                }}
                onKeyDown={(event) => {
                  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                    event.preventDefault();
                    const next = visible.length
                      ? (selected + (event.key === 'ArrowDown' ? 1 : -1) + visible.length) %
                        visible.length
                      : 0;
                    setSelected(next);
                    if (visible[next])
                      document
                        .getElementById(`command-${visible[next].route}`)
                        ?.scrollIntoView({ block: 'nearest' });
                  }
                  if (event.key === 'Enter') {
                    event.preventDefault();
                    if (active) choose(active.route);
                  }
                }}
              />
              <div
                className="cn-input-group-addon flex cursor-text select-none items-center justify-center cn-input-group-addon-align-inline-start order-first"
                data-align="inline-start"
                data-slot="input-group-addon"
                role="group"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  width="24"
                  height="24"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="lucide lucide-search cn-command-input-icon"
                  aria-hidden="true"
                >
                  <path d="m21 21-4.34-4.34" />
                  <circle cx="11" cy="11" r="8" />
                </svg>
              </div>
            </div>
          </div>
          <div
            className="cn-command-list overflow-y-auto overflow-x-hidden"
            data-slot="command-list"
            cmdk-list=""
            role="listbox"
            tabIndex={-1}
            aria-label="Suggestions"
            id="command-suggestions"
            style={{ '--cmdk-list-height': '396.0px' } as CSSProperties}
          >
            <div cmdk-list-sizer="">
              {groups.map((group) => (
                <div
                  key={group.label}
                  className="cn-command-group"
                  data-slot="command-group"
                  cmdk-group=""
                  role="presentation"
                  data-value={group.label}
                  hidden={!group.items.some((item) => visible.includes(item))}
                >
                  <div cmdk-group-heading="" aria-hidden="true" id={`command-group-${group.label}`}>
                    {group.label}
                  </div>
                  <div
                    cmdk-group-items=""
                    role="group"
                    aria-labelledby={`command-group-${group.label}`}
                  >
                    {group.items.map((item) => (
                      <div
                        key={item.route}
                        className="cn-command-item group/command-item data-[disabled=true]:pointer-events-none data-[disabled=true]:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0"
                        data-slot="command-item"
                        id={`command-${item.route}`}
                        cmdk-item=""
                        role="option"
                        aria-disabled="false"
                        aria-selected={item === active}
                        data-disabled="false"
                        data-selected={String(item === active)}
                        data-value={item.label}
                        hidden={!visible.includes(item)}
                        onPointerMove={() => setSelected(visible.indexOf(item))}
                        onClick={() => choose(item.route)}
                      >
                        {item.icon}
                        <span>{item.label}</span>
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          width="24"
                          height="24"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          className="lucide lucide-square cn-command-item-indicator ml-auto opacity-0 group-has-[[data-slot=command-shortcut]]/command-item:hidden group-data-[checked=true]/command-item:opacity-100"
                          aria-hidden="true"
                        >
                          <rect width="18" height="18" x="3" y="3" rx="2" />
                        </svg>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
            <div className="search-empty" hidden={visible.length > 0}>
              No results found.
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
