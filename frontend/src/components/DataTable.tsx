import type { HTMLAttributes, ComponentProps } from 'react';
import { ScrollArea } from './ScrollArea';

export function TablePanel({ children, className = '', ...props }: HTMLAttributes<HTMLElement>) {
  return (
    <section className={`cn-card data-table-panel ${className}`} {...props}>
      {children}
    </section>
  );
}
export function TableBody({
  empty,
  cardContent,
  className = '',
  ...props
}: Omit<ComponentProps<typeof ScrollArea>, 'overlay' | 'viewportClassName' | 'contentSlot'> & {
  empty: React.ReactNode;
  cardContent?: boolean;
}) {
  return (
    <ScrollArea
      {...props}
      className={`data-table-body ${className}`}
      viewportClassName={`${cardContent ? 'cn-card-content ' : ''}bag-table-scroll`}
      contentSlot={cardContent ? 'card-content' : undefined}
      overlay={empty}
    />
  );
}
export function EmptyState({ hidden, children, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className="bag-empty" role="status" hidden={hidden} {...props}>
      {children}
    </div>
  );
}
