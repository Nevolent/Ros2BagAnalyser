import type { ThHTMLAttributes } from 'react';
import type { SortState } from '../lib/useTableSort';

export function SortableHeader<Key extends string>({
  column,
  sort,
  onSort,
  children,
  ...props
}: ThHTMLAttributes<HTMLTableCellElement> & {
  column: Key;
  sort: SortState<Key>;
  onSort(key: Key): void;
}) {
  const direction = sort?.key === column ? sort.direction : 'none';
  return (
    <th {...props} scope="col" aria-sort={direction}>
      <button
        type="button"
        className="table-sort"
        onClick={() => onSort(column)}
        title={
          direction === 'none'
            ? 'Sort ascending'
            : direction === 'ascending'
              ? 'Sort descending'
              : 'Restore original order'
        }
      >
        <span>{children}</span>
        <svg
          viewBox="0 0 12 16"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path className="sort-up" d="m3 6 3-3 3 3" />
          <path className="sort-down" d="m3 10 3 3 3-3" />
        </svg>
      </button>
    </th>
  );
}
