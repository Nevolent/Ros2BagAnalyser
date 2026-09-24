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
}: {
  children: ReactNode;
  empty: ReactNode;
  label: string;
  className?: string;
  id?: string;
  scrollRef?: Ref<HTMLDivElement>;
  cardContent?: boolean;
}) {
  return (
    <div className={`data-table-body ${className}`} id={id}>
      <div
        ref={scrollRef}
        className={`${cardContent ? 'cn-card-content ' : ''}bag-table-scroll`}
        data-slot={cardContent ? 'card-content' : undefined}
        role="region"
        aria-label={label}
        tabIndex={0}
      >
        {children}
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
