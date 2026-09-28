import { useCallback, useLayoutEffect, useRef, useState, type ReactNode, type Ref } from 'react';
import { useRememberedState } from '../app/WorkspaceProvider';

export function ScrollArea({
  children,
  overlay,
  label,
  className = '',
  id,
  scrollRef,
  viewportClassName = '',
  contentSlot,
  scrollbarHeaderGap = 0,
  gutter = false,
}: {
  children: ReactNode;
  overlay?: ReactNode;
  label: string;
  className?: string;
  id?: string;
  scrollRef?: Ref<HTMLDivElement>;
  viewportClassName?: string;
  contentSlot?: string;
  scrollbarHeaderGap?: number;
  gutter?: boolean;
}) {
  const [position, setPosition] = useRememberedState(`scroll.${label}`, { top: 0, left: 0 });
  const restore = useRef(true);
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
    if (restore.current && (element.scrollHeight > element.clientHeight || !position.top)) {
      element.scrollTop = position.top;
      element.scrollLeft = position.left;
      restore.current = false;
    }
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
      ? (Math.max(0, Math.min(element.scrollTop, element.scrollHeight - element.clientHeight)) /
          (element.scrollHeight - element.clientHeight)) *
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
  }, [scrollbarHeaderGap, position]);
  useLayoutEffect(() => {
    const element = viewport.current;
    if (!element) return;
    const observer = new ResizeObserver(updateScrollbar);
    observer.observe(element);
    const content = element.firstElementChild;
    if (content) observer.observe(content);
    const mutations = new MutationObserver(updateScrollbar);
    mutations.observe(element, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ['hidden'],
    });
    updateScrollbar();
    return () => {
      observer.disconnect();
      mutations.disconnect();
    };
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
    if (height <= scrollbar.height) return;
    element.scrollTop =
      ((clientY - top - dragOffset.current) / (height - scrollbar.height)) *
      (element.scrollHeight - element.clientHeight);
  };
  return (
    <div className={`scroll-area${gutter ? ' scroll-area-gutter' : ''} ${className}`} id={id}>
      <div
        ref={setViewport}
        className={`scroll-viewport ${viewportClassName}${scrollbar.overlay ? ' has-overlay-scrollbar' : ''}`}
        data-slot={contentSlot}
        role="region"
        aria-label={label}
        tabIndex={0}
        onScroll={() => {
          if (!restore.current)
            setPosition({ top: viewport.current!.scrollTop, left: viewport.current!.scrollLeft });
          updateScrollbar();
        }}
      >
        {children}
      </div>
      <div
        className="scrollbar-track"
        style={{ top: scrollbar.trackTop }}
        data-visible={scrollbar.overlay}
        aria-hidden="true"
      >
        <div
          ref={track}
          className="scrollbar-rail"
          style={{ top: 0, bottom: 0 }}
          onPointerDown={(event) => {
            if (event.button !== 0) return;
            event.preventDefault();
            viewport.current?.focus({ preventScroll: true });
            const thumb = event.currentTarget.firstElementChild!.getBoundingClientRect();
            dragOffset.current =
              event.clientY >= thumb.top && event.clientY <= thumb.bottom
                ? event.clientY - thumb.top
                : scrollbar.height / 2;
            event.currentTarget.setPointerCapture(event.pointerId);
            moveScrollbar(event.clientY);
          }}
          onPointerUp={(event) => {
            if (event.currentTarget.hasPointerCapture(event.pointerId))
              event.currentTarget.releasePointerCapture(event.pointerId);
          }}
          onPointerMove={(event) => {
            if (event.currentTarget.hasPointerCapture(event.pointerId))
              moveScrollbar(event.clientY);
          }}
        >
          <div
            className="scrollbar-thumb"
            style={{ height: scrollbar.height, top: scrollbar.top }}
          />
        </div>
      </div>
      {overlay}
    </div>
  );
}
