import type { InputHTMLAttributes, Ref } from 'react';
import { Icon } from './Icon';
export function SearchField({
  className,
  inputClassName,
  inputRef,
  onChange,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & {
  inputClassName?: string;
  inputRef?: Ref<HTMLInputElement>;
}) {
  return (
    <label className={`${className ?? ''} search-field`}>
      <Icon name="search" strokeLinejoin={undefined} />
      <input
        ref={inputRef}
        className={inputClassName}
        type="search"
        {...props}
        onChange={onChange}
      />
      <button
        type="button"
        className="search-clear"
        aria-label="Clear search"
        title="Clear search"
        onClick={(event) => {
          const input = event.currentTarget.parentElement!.querySelector('input')!;
          const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
          setter.call(input, '');
          input.dispatchEvent(new Event('input', { bubbles: true }));
          input.focus();
        }}
      >
        <Icon name="cancel" strokeWidth={1.5} />
      </button>
    </label>
  );
}
