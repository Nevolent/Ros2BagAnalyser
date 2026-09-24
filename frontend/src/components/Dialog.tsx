import { useLayoutEffect, useRef, type ReactNode, type FormEvent } from 'react';
import { createPortal } from 'react-dom';
export function Dialog({
  open,
  onClose,
  labelledBy,
  describedBy,
  className = '',
  children,
  onSubmit,
  initialFocus,
}: {
  open: boolean;
  onClose(): void;
  labelledBy: string;
  describedBy?: string;
  className?: string;
  children: ReactNode;
  onSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  initialFocus?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useLayoutEffect(() => {
    const dialog = ref.current!;
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    dialog.showModal();
    if (initialFocus) dialog.querySelector<HTMLElement>(initialFocus)?.focus();
    return () => {
      dialog.close();
      if (previous?.isConnected) previous.focus({ preventScroll: true });
    };
  }, [open, initialFocus]);
  return createPortal(
    <dialog
      ref={ref}
      className={`recordings-prepare-dialog ${className}`}
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      onCancel={(event) => {
        event.preventDefault();
        closeRef.current();
      }}
      onClick={(event) => {
        if (event.target !== event.currentTarget) return;
        const rect = event.currentTarget.getBoundingClientRect();
        if (
          event.clientX < rect.left ||
          event.clientX > rect.right ||
          event.clientY < rect.top ||
          event.clientY > rect.bottom
        )
          closeRef.current();
      }}
    >
      <form
        method="dialog"
        onSubmit={(event) => {
          event.preventDefault();
          if (onSubmit) onSubmit(event);
          else closeRef.current();
        }}
      >
        {children}
      </form>
    </dialog>,
    document.body,
  );
}
