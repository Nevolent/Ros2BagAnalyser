import type { ReactNode } from 'react';
/** Use semantic tones so statuses inherit the shared palette. */
export function StatusBadge({
  tone = 'muted',
  children,
}: {
  tone?: 'success' | 'error' | 'muted';
  children: ReactNode;
}) {
  return <span className={`bag-status status-${tone}`}>{children}</span>;
}
