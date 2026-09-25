import { Fragment, type RefObject } from 'react';
/** Compact page tabs use one geometry and keyboard-visible button treatment. */
export function Tabs<T extends string>({
  label,
  items,
  value,
  onChange,
  controls,
  firstRef,
}: {
  label: string;
  items: readonly { value: T; label: string; count?: number }[];
  value: T;
  onChange(value: T): void;
  controls: string;
  firstRef?: RefObject<HTMLButtonElement | null>;
}) {
  return (
    <div className="page-tabs" role="group" aria-label={label}>
      {items.map((item, index) => (
        <Fragment key={item.value}>
          {index > 0 && <span aria-hidden="true">/</span>}
          <button
            ref={index === 0 ? firstRef : undefined}
            type="button"
            data-tab={item.value}
            aria-pressed={value === item.value}
            aria-controls={controls}
            onClick={() => onChange(item.value)}
          >
            <span>{item.label}</span>
            {item.count !== undefined && (
              <span className="page-tab-count" aria-hidden="true">
                <span>{item.count}</span>
              </span>
            )}
          </button>
        </Fragment>
      ))}
    </div>
  );
}
