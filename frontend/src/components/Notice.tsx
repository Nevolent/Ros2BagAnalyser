import { useEffect } from 'react';
import { createPortal } from 'react-dom';
export function Notice({ message, onDismiss }: { message: string; onDismiss(): void }) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, 4000);
    return () => clearTimeout(timer);
  }, [message, onDismiss]);
  return createPortal(
    <div className="recordings-notice" role="status">
      {message}
    </div>,
    document.body,
  );
}
