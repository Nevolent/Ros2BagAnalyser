import type { ReactNode } from 'react';
export function Page({
  name,
  title,
  actions,
  breadcrumb,
  children,
}: {
  name: string;
  title: string;
  actions?: ReactNode;
  breadcrumb?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className={`dashboard-content ${name}-content`}>
      <div
        className={`page-header${actions ? ' flex flex-wrap items-center justify-between gap-3' : ''}`}
      >
        <h1 className="text-balance font-medium text-lg tracking-tight">{title}</h1>
        {breadcrumb}
        {actions}
      </div>
      {children}
    </div>
  );
}
