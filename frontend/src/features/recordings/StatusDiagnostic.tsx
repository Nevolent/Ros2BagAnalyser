import { conciseIssues } from '../../data/diagnostics';
import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import type { Recording } from '../../data/types';

let activeDiagnostic: { id: string; close: () => void } | null = null;

/** Keep diagnostics outside the scrolling table so the left-hand popup is never clipped. */
export function StatusDiagnostic({
  status,
  issues,
  tone = 'error',
  outputs,
}: {
  status: string;
  issues: string[];
  tone?: 'error' | 'success';
  outputs?: Recording['analysisOutputs'];
}) {
  const visibleOutputs = outputs?.filter((output) => output.state !== 'unavailable');
  const id = useId();
  const target = useRef<HTMLButtonElement>(null);
  const popup = useRef<HTMLDivElement>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [open, setOpen] = useState(false);
  function show() {
    clearTimeout(hideTimer.current);
    if (activeDiagnostic?.id !== id) activeDiagnostic?.close();
    activeDiagnostic = { id, close: hide };
    setOpen(true);
  }
  function hide() {
    clearTimeout(hideTimer.current);
    if (activeDiagnostic?.id === id) activeDiagnostic = null;
    setOpen(false);
  }
  function leave() {
    clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => {
      if (document.activeElement !== target.current) hide();
    }, 100);
  }
  useLayoutEffect(() => {
    if (!open || !popup.current || !target.current) return;
    const anchor = target.current.getBoundingClientRect();
    const rect = popup.current.getBoundingClientRect();
    const left = Math.max(8, anchor.left - rect.width - 8);
    const top = Math.max(
      8,
      Math.min(
        innerHeight - rect.height - 8,
        left + rect.width <= anchor.left
          ? anchor.top + (anchor.height - rect.height) / 2
          : anchor.bottom + 8,
      ),
    );
    popup.current.style.left = `${left}px`;
    popup.current.style.top = `${top}px`;
  }, [open, issues, outputs]);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    const { signal } = controller;
    document.addEventListener(
      'keydown',
      (event) => {
        if (event.key === 'Escape') hide();
      },
      { signal },
    );
    document.addEventListener(
      'scroll',
      (event) => {
        if (!(event.target instanceof Node) || !popup.current?.contains(event.target)) hide();
      },
      { capture: true, signal },
    );
    window.addEventListener('resize', hide, { signal });
    return () => controller.abort();
  }, [open]);
  useEffect(
    () => () => {
      clearTimeout(hideTimer.current);
      if (activeDiagnostic?.id === id) activeDiagnostic = null;
    },
    [id],
  );
  return (
    <>
      <button
        type="button"
        ref={target}
        className={`bag-status status-${tone} recording-status-diagnostic`}
        tabIndex={0}
        aria-describedby={open ? id : undefined}
        onPointerEnter={show}
        onPointerLeave={leave}
        onClick={(event) => {
          event.stopPropagation();
          show();
        }}
        onFocus={show}
        onBlur={leave}
      >
        {status}
      </button>
      {open &&
        createPortal(
          <div
            ref={popup}
            id={id}
            role="tooltip"
            className={`recording-diagnostic-tooltip status-${tone}`}
            onPointerEnter={show}
            onPointerLeave={leave}
          >
            {visibleOutputs?.length
              ? visibleOutputs.map((output) => (
                  <p
                    key={output.name}
                    data-output-state={output.state}
                    className={output.state === 'ready' ? 'status-success' : 'status-muted'}
                  >
                    {output.name}
                    <span className="sr-only">
                      {' '}
                      — {output.state === 'ready' ? 'Prepared' : 'Needs preparation'}
                    </span>
                  </p>
                ))
              : conciseIssues(issues).map((issue, index) => <p key={index}>{issue}</p>)}
          </div>,
          document.body,
        )}
    </>
  );
}
