import {
  useLayoutEffect,
  useRef,
  type RefObject,
  type ReactNode,
  type HTMLAttributes,
} from 'react';
import { createPortal } from 'react-dom';
export function Popover({
  anchor,
  onClose,
  align = 'left',
  children,
  ...props
}: HTMLAttributes<HTMLDivElement> & {
  anchor: RefObject<HTMLElement | null>;
  onClose(restoreFocus?: boolean): void;
  align?: 'left' | 'right';
  children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useLayoutEffect(() => {
    const panel = ref.current!,
      trigger = anchor.current!;
    const rect = trigger.getBoundingClientRect();
    panel.style.left = `${Math.max(8, Math.min(innerWidth - panel.offsetWidth - 8, align === 'right' ? rect.right - panel.offsetWidth : rect.left))}px`;
    panel.style.top = `${Math.max(8, Math.min(innerHeight - panel.offsetHeight - 8, rect.bottom + (align === 'right' ? 6 : 4)))}px`;
    (panel.querySelector<HTMLElement>('[aria-checked="true"]') ?? panel).focus();
    const controller = new AbortController();
    const { signal } = controller;
    document.addEventListener(
      'pointerdown',
      (event) => {
        if (!panel.contains(event.target as Node) && !trigger.contains(event.target as Node))
          close.current(false);
      },
      { signal },
    );
    document.addEventListener(
      'keydown',
      (event) => {
        if (event.key === 'Escape') {
          event.preventDefault();
          close.current(true);
        }
        if (event.key === 'Tab') close.current(false);
      },
      { signal },
    );
    window.addEventListener('resize', () => close.current(false), { signal });
    return () => controller.abort();
  }, [anchor, align]);
  return createPortal(
    <div ref={ref} tabIndex={-1} {...props}>
      {children}
    </div>,
    document.body,
  );
}
