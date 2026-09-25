import { useCallback, useLayoutEffect, useRef, useState } from 'react';
import type { HTMLAttributes, ReactNode, Ref } from 'react';

export function TablePanel({ children, className = '', ...props }: HTMLAttributes<HTMLElement>) {
  return (
    <section className={`cn-card data-table-panel ${className}`} {...props}>
      {children}
    </section>
  );
}
export function TableBody({
  children,
  empty,
  label,
  className = '',
  id,
  scrollRef,
  cardContent = false,
  scrollbarHeaderGap = 0,
}: {
  children: ReactNode;
  empty: ReactNode;
  label: string;
  className?: string;
  id?: string;
  scrollRef?: Ref<HTMLDivElement>;
  cardContent?: boolean;
  scrollbarHeaderGap?: number;
}) {
  const viewport = useRef<HTMLDivElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const dragOffset = useRef(0);
  const [scrollbar, setScrollbar] = useState({
    overlay: false,
    top: 0,
    height: 0,
    trackTop: 4,
  });
  const updateScrollbar = useCallback(() => {
    const element = viewport.current;
    const trackElement = track.current;
    if (!element || !trackElement) return;
    const body = element.parentElement;
    if (!body) return;
    // Keep native scrollbars when the table needs horizontal scrolling.
    const overlay =
      element.scrollWidth <= element.clientWidth + 1 &&
      element.scrollHeight > element.clientHeight + 1;
    const headerCell = element.querySelector<HTMLTableCellElement>('thead th');
    const bodyTop = body.getBoundingClientRect().top;
    const trackTop = headerCell
      ? Math.max(4, headerCell.getBoundingClientRect().bottom - bodyTop + scrollbarHeaderGap)
      : Math.max(4, scrollbarHeaderGap);
    const trackHeight = Math.max(0, body.clientHeight - trackTop - 4);
    const height = overlay
      ? Math.min(
          trackHeight,
          Math.max(28, (trackHeight * element.clientHeight) / element.scrollHeight),
        )
      : 0;
    const top = overlay
      ? (element.scrollTop / (element.scrollHeight - element.clientHeight)) *
        Math.max(0, trackHeight - height)
      : 0;
    setScrollbar((previous) =>
      previous.overlay === overlay &&
      previous.top === top &&
      previous.height === height &&
      previous.trackTop === trackTop
        ? previous
        : { overlay, top, height, trackTop },
    );
  }, [scrollbarHeaderGap]);
  useLayoutEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const observer = new ResizeObserver(updateScrollbar);
    observer.observe(element);
    const table = element.querySelector('table');
    if (table) observer.observe(table);
    updateScrollbar();
    return () => observer.disconnect();
  }, [children, updateScrollbar]);
  const setViewport = useCallback(
    (element: HTMLDivElement | null) => {
      viewport.current = element;
      if (typeof scrollRef === 'function') scrollRef(element);
      else if (scrollRef) scrollRef.current = element;
    },
    [scrollRef],
  );
  const moveScrollbar = (clientY: number) => {
    const element = viewport.current;
    const trackElement = track.current;
    if (!element || !trackElement) return;
    const { top, height } = trackElement.getBoundingClientRect();
    element.scrollTop =
      ((clientY - top - dragOffset.current) / (height - scrollbar.height)) *
      (element.scrollHeight - element.clientHeight);
  };
  return (
    <div className={`data-table-body ${className}`} id={id}>
      <div
        ref={setViewport}
        className={`${cardContent ? 'cn-card-content ' : ''}bag-table-scroll${scrollbar.overlay ? ' has-overlay-scrollbar' : ''}`}
        data-slot={cardContent ? 'card-content' : undefined}
        role="region"
        aria-label={label}
        tabIndex={0}
        onScroll={updateScrollbar}
      >
        {children}
      </div>
      <div
        className="table-scrollbar-track"
        style={{ top: scrollbar.trackTop }}
        data-visible={scrollbar.overlay}
        aria-hidden="true"
      >
        <div
          ref={track}
          className="table-scrollbar-rail"
          style={{ top: 0, bottom: 4 }}
          onPointerDown={(event) => {
            const thumb = event.currentTarget.firstElementChild!.getBoundingClientRect();
            dragOffset.current =
              event.clientY >= thumb.top && event.clientY <= thumb.bottom
                ? event.clientY - thumb.top
                : scrollbar.height / 2;
            event.currentTarget.setPointerCapture(event.pointerId);
            moveScrollbar(event.clientY);
          }}
          onPointerMove={(event) => {
            if (event.currentTarget.hasPointerCapture(event.pointerId)) moveScrollbar(event.clientY);
          }}
        >
          <div
            className="table-scrollbar-thumb"
            style={{ height: scrollbar.height, top: scrollbar.top }}
          />
        </div>
      </div>
      {empty}
    </div>
  );
}
export function EmptyState({ hidden, children, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className="bag-empty" role="status" hidden={hidden} {...props}>
      {children}
    </div>
  );
}
