import { useMemo, useState } from 'react';

export type SortState<Key extends string> = {
  key: Key;
  direction: 'ascending' | 'descending';
} | null;
export type SortAccessors<Item, Key extends string> = Record<Key, (item: Item) => string | number>;
const collator = new Intl.Collator('en', { numeric: true, sensitivity: 'base' });

/** Sorting changes the view only; a third click restores the source order. */
export function useTableSort<Item, Key extends string>(
  items: Item[],
  accessors: SortAccessors<Item, Key>,
) {
  const [sort, setSort] = useState<SortState<Key>>(null);
  const sorted = useMemo(() => {
    if (!sort) return items;
    const value = accessors[sort.key];
    const direction = sort.direction === 'ascending' ? 1 : -1;
    return [...items].sort((a, b) => {
      const left = value(a),
        right = value(b);
      return (
        direction *
        (typeof left === 'number' && typeof right === 'number'
          ? left - right
          : collator.compare(String(left), String(right)))
      );
    });
  }, [items, accessors, sort]);
  function toggle(key: Key) {
    setSort((current) =>
      current?.key !== key
        ? { key, direction: 'ascending' }
        : current.direction === 'ascending'
          ? { key, direction: 'descending' }
          : null,
    );
  }
  return { sorted, sort, toggle, reset: () => setSort(null) };
}

export function sizeInBytes(size: string) {
  const [amount, unit = 'B'] = size.trim().split(/\s+/);
  const powers: Record<string, number> = {
    B: 1,
    KB: 1e3,
    MB: 1e6,
    GB: 1e9,
    TB: 1e12,
    KiB: 1024,
    MiB: 1024 ** 2,
    GiB: 1024 ** 3,
    TiB: 1024 ** 4,
  };
  return Number(amount) * (powers[unit] ?? 1);
}

export function durationInSeconds(duration: string) {
  return duration.split(':').reduce((seconds, part) => seconds * 60 + Number(part), 0);
}
