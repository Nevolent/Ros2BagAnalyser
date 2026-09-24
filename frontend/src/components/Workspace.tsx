import {
  createContext,
  useContext,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
  type RefObject,
} from 'react';

interface PanelContext {
  collapsed: boolean;
  width: number | undefined;
  side: 'left' | 'right';
  toggle: RefObject<HTMLButtonElement | null>;
  setCollapsed(value: boolean): void;
}
const PanelContext = createContext<PanelContext | null>(null);
export function useWorkspacePanel() {
  const value = useContext(PanelContext);
  if (!value) throw new Error('SidePanel requires a Workspace.');
  return value;
}
export function Workspace({
  name,
  side = 'left',
  panelLabel = 'folders',
  children,
  rootRef,
}: {
  name: string;
  side?: 'left' | 'right';
  panelLabel?: string;
  children: ReactNode;
  rootRef?: RefObject<HTMLDivElement | null>;
}) {
  const localRoot = useRef<HTMLDivElement>(null);
  const root = rootRef ?? localRoot;
  const splitter = useRef<HTMLDivElement>(null);
  const toggle = useRef<HTMLButtonElement>(null);
  const reopen = useRef<HTMLButtonElement>(null);
  const [collapsed, updateCollapsed] = useState(false);
  const [resizing, setResizing] = useState(false);
  const [width, setWidth] = useState<number>();
  const [maximum, setMaximum] = useState(side === 'right' ? 280 : 160);
  const focusPending = useRef(false);
  const minimum = side === 'right' ? 280 : 160;
  function maxWidth() {
    const element = root.current!;
    const table = element.querySelector<HTMLElement>('.bag-table');
    const scroll = table?.closest<HTMLElement>('.bag-table-scroll');
    if (name === 'recordings' && table && scroll) {
      const style = getComputedStyle(scroll);
      const tableWidth =
        parseFloat(getComputedStyle(table).minWidth) +
        parseFloat(style.paddingLeft) +
        parseFloat(style.paddingRight) +
        scroll.offsetWidth -
        scroll.clientWidth;
      return Math.max(
        minimum,
        element.clientWidth - tableWidth - (splitter.current?.offsetWidth ?? 8),
      );
    }
    return Math.max(minimum, element.clientWidth - 260);
  }
  function resize(next: number) {
    const max = maxWidth();
    setMaximum(max);
    setWidth(Math.max(minimum, Math.min(max, next)));
  }
  useLayoutEffect(() => {
    const element = root.current!;
    const observer = new ResizeObserver(() => {
      if (matchMedia('(max-width:600px)').matches) return;
      resize(parseFloat(getComputedStyle(element).getPropertyValue('--folder-width')));
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [name, side]);
  useLayoutEffect(() => {
    if (focusPending.current) {
      (collapsed ? reopen : toggle).current?.focus({ preventScroll: true });
      focusPending.current = false;
    }
  }, [collapsed]);
  return (
    <PanelContext.Provider
      value={{
        collapsed,
        width,
        side,
        toggle,
        setCollapsed(value) {
          focusPending.current = true;
          updateCollapsed(value);
        },
      }}
    >
      <div
        ref={root}
        className={`dashboard-workspace ${name}-workspace${collapsed ? ' is-folder-collapsed' : ''}${resizing ? ' is-resizing' : ''}`}
        style={
          width === undefined ? undefined : ({ '--folder-width': `${width}px` } as CSSProperties)
        }
      >
        {children}
        <div
          ref={splitter}
          className="workspace-splitter"
          role="separator"
          aria-label={`Resize ${panelLabel}`}
          aria-orientation="vertical"
          tabIndex={0}
          data-workspace-splitter=""
          aria-valuemin={minimum}
          aria-valuemax={Math.round(maximum)}
          aria-valuenow={Math.round(width ?? (side === 'right' ? 320 : 256))}
          inert={collapsed}
          onPointerDown={(event) => {
            if (event.button !== 0) return;
            event.preventDefault();
            event.currentTarget.setPointerCapture(event.pointerId);
            setResizing(true);
          }}
          onPointerMove={(event) => {
            if (!event.currentTarget.hasPointerCapture(event.pointerId)) return;
            const rect = root.current!.getBoundingClientRect();
            resize(
              side === 'right' ? rect.right - event.clientX - 4 : event.clientX - rect.left - 4,
            );
          }}
          onPointerUp={() => setResizing(false)}
          onPointerCancel={() => setResizing(false)}
          onLostPointerCapture={() => setResizing(false)}
          onKeyDown={(event) => {
            if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
            event.preventDefault();
            const current = root
              .current!.querySelector('.folder-card')!
              .getBoundingClientRect().width;
            resize(current + (event.key === 'ArrowRight' ? 16 : -16) * (side === 'right' ? -1 : 1));
          }}
        />
        <button
          ref={reopen}
          className="folder-reopen"
          type="button"
          data-folder-reopen=""
          aria-label={`Expand ${panelLabel}`}
          aria-controls="folder-panel"
          hidden={!collapsed}
          onClick={() => {
            focusPending.current = true;
            updateCollapsed(false);
          }}
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d={side === 'right' ? 'm15 5-7 7 7 7' : 'm9 5 7 7-7 7'} />
          </svg>
          <span className="folder-reopen-label">
            {side === 'right' ? 'Recording details' : 'Browse folders'}
          </span>
        </button>
      </div>
    </PanelContext.Provider>
  );
}
export function SidePanel({
  title,
  children,
  selectedFolder,
}: {
  title: string;
  children: ReactNode;
  selectedFolder?: string;
}) {
  const { collapsed, setCollapsed, side, toggle } = useWorkspacePanel();
  const control = (
    <button
      ref={toggle}
      className="folder-toggle"
      type="button"
      data-folder-toggle=""
      aria-label={`Collapse ${title.toLowerCase()}`}
      title={`Hide ${title.toLowerCase()}`}
      aria-expanded={!collapsed}
      aria-controls="folder-panel"
      onClick={() => setCollapsed(true)}
    >
      <svg
        aria-hidden="true"
        className="size-5 text-muted-foreground"
        fill="currentColor"
        focusable="false"
        height="16"
        role="img"
        viewBox="0 0 16 16"
        width="16"
        xmlns="http://www.w3.org/2000/svg"
      >
        <g>
          <path
            clipRule="evenodd"
            d="M4.25 2C2.45508 2 1 3.45508 1 5.25V10.75C1 12.5449 2.45508 14 4.25 14H11.75C13.5449 14 15 12.5449 15 10.75V5.25C15 3.45508 13.5449 2 11.75 2H4.25ZM2.5 5.5C2.5 4.39543 3.39543 3.5 4.5 3.5H11.5C12.6046 3.5 13.5 4.39543 13.5 5.5V10.5C13.5 11.6046 12.6046 12.5 11.5 12.5H4.5C3.39543 12.5 2.5 11.6046 2.5 10.5V5.5Z"
            fillRule="evenodd"
          />
          <rect
            className={
              side === 'right'
                ? 'transition-[width] duration-(--sidebar-animation-duration) ease-(--sidebar-animation-ease)'
                : undefined
            }
            height="6"
            rx="0.75"
            width="1.5"
            x={side === 'right' ? '10.5' : '4'}
            y="5"
          />
        </g>
      </svg>
    </button>
  );
  return (
    <aside
      className="cn-card folder-card bg-secondary shadow-none ring-0 dark:bg-secondary/50"
      data-slot="card"
      id="folder-panel"
      aria-labelledby="folder-heading"
      data-selected-folder={selectedFolder}
      inert={collapsed}
    >
      <div className="folder-heading">
        <h2 id="folder-heading">{title}</h2>
        {side === 'left' ? <div className="folder-heading-actions">{control}</div> : control}
      </div>
      {children}
    </aside>
  );
}
