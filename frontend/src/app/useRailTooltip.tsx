import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type PointerEvent,
  type FocusEvent,
} from 'react';
import { createPortal } from 'react-dom';
export function useRailTooltip() {
  const [hint, setHint] = useState<{ target: HTMLElement; text: string; leaving: boolean } | null>(
    null,
  );
  const current = useRef(hint);
  current.current = hint;
  const ref = useRef<HTMLDivElement>(null);
  const showTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  function hide() {
    clearTimeout(showTimer.current);
    clearTimeout(hideTimer.current);
    setHint(null);
  }
  function show(target: HTMLElement) {
    clearTimeout(hideTimer.current);
    clearTimeout(showTimer.current);
    const text = target.hasAttribute('data-rail-logo')
      ? 'Tectrace'
      : target.getAttribute('aria-label')!;
    const next = { target, text, leaving: false };
    if (current.current) {
      if (current.current.target === target && !current.current.leaving) return;
      setHint(next);
    } else showTimer.current = setTimeout(() => setHint(next), 40);
  }
  function scheduleHide(delay = 70) {
    clearTimeout(showTimer.current);
    clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => {
      setHint((current) => (current ? { ...current, leaving: true } : null));
      hideTimer.current = setTimeout(hide, 160);
    }, delay);
  }
  useLayoutEffect(() => {
    if (!hint || !ref.current) return;
    const rect = hint.target.getBoundingClientRect();
    const label = ref.current.firstElementChild as HTMLElement;
    ref.current.style.width = `${label.offsetWidth + 22}px`;
    ref.current.style.left = `${rect.right + 7}px`;
    ref.current.style.top = `${Math.max(8, rect.top + (rect.height - ref.current.offsetHeight) / 2)}px`;
    hint.target.setAttribute('aria-describedby', 'control-hint');
    return () => hint.target.removeAttribute('aria-describedby');
  }, [hint]);
  useEffect(() => {
    const controller = new AbortController();
    document.addEventListener(
      'keydown',
      (event) => {
        if (event.key === 'Escape') hide();
      },
      { signal: controller.signal },
    );
    window.addEventListener('resize', hide, { signal: controller.signal });
    return () => {
      controller.abort();
      clearTimeout(showTimer.current);
      clearTimeout(hideTimer.current);
    };
  }, []);
  return {
    events: {
      onPointerOver(event: PointerEvent) {
        const target = (event.target as HTMLElement).closest<HTMLElement>(
          '[data-rail-link],[data-rail-logo]',
        );
        if (target) show(target);
      },
      onPointerOut(event: PointerEvent) {
        const target = (event.target as HTMLElement).closest('[data-rail-link],[data-rail-logo]');
        if (
          target &&
          !(event.relatedTarget instanceof Node && target.contains(event.relatedTarget))
        ) {
          const rect = target.getBoundingClientRect();
          const crossingLogoGap =
            (target.hasAttribute('data-rail-logo') && event.clientY >= rect.bottom) ||
            (target.getAttribute('aria-label') === 'Recordings' && event.clientY <= rect.top);
          scheduleHide(crossingLogoGap ? 220 : 70);
        }
      },
      onFocus(event: FocusEvent) {
        const target = (event.target as HTMLElement).closest<HTMLElement>(
          '[data-rail-link],[data-rail-logo]',
        );
        if (target) show(target);
      },
      onBlur: () => scheduleHide(),
    },
    tooltip:
      hint &&
      createPortal(
        <div
          ref={ref}
          className={`info-tooltip rail-tooltip${hint.leaving ? ' is-leaving' : ''}`}
          id="control-hint"
          role="tooltip"
        >
          <span className="rail-tooltip-label" key={hint.text}>
            {hint.text}
          </span>
        </div>,
        document.body,
      ),
  };
}
