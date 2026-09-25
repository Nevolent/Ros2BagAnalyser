import { useRef, useState } from 'react';
import { Icon } from './Icon';
import { Popover } from './Popover';
export function FilterMenu({
  label,
  name,
  options,
  value,
  onChange,
}: {
  label: string;
  name: string;
  options: string[];
  value: string;
  onChange(value: string): void;
}) {
  const [open, setOpen] = useState(false);
  const anchor = useRef<HTMLButtonElement>(null);
  function close(restore = false) {
    setOpen(false);
    if (restore) anchor.current?.focus();
  }
  const values = ['', ...options];
  return (
    <div className="bag-filter">
      <button
        ref={anchor}
        type="button"
        aria-label={`Filter by ${name}`}
        aria-haspopup="menu"
        aria-expanded={open}
        data-filter-trigger={name}
        data-filter-value={value || undefined}
        onClick={() => setOpen(!open)}
      >
        {value || label}
        <Icon name="chevron" strokeWidth={2} />
      </button>
      <select
        hidden
        aria-label={`${label} value`}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        {...{ [`data-bag-${name}-filter`]: '' }}
      >
        {values.map((item) => (
          <option key={item} value={item}>
            {item || label}
          </option>
        ))}
      </select>
      {open && (
        <Popover
          anchor={anchor}
          onClose={close}
          className="bag-filter-menu"
          role="menu"
          aria-label={`Filter by ${name}`}
          onKeyDown={(event) => {
            const items = Array.from(event.currentTarget.querySelectorAll('button'));
            const current = items.indexOf(document.activeElement as HTMLButtonElement);
            const next =
              event.key === 'ArrowDown'
                ? (current + 1) % items.length
                : event.key === 'ArrowUp'
                  ? (current + items.length - 1) % items.length
                  : event.key === 'Home'
                    ? 0
                    : event.key === 'End'
                      ? items.length - 1
                      : undefined;
            if (next !== undefined) {
              event.preventDefault();
              items[next].focus();
            }
          }}
        >
          {values.map((item) => (
            <button
              type="button"
              role="menuitemradio"
              aria-checked={value === item}
              data-filter-option={item || undefined}
              key={item}
              onClick={() => {
                onChange(item);
                close(true);
              }}
            >
              {item || label}
            </button>
          ))}
        </Popover>
      )}
    </div>
  );
}
