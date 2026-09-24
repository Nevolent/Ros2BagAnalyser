import type { InputHTMLAttributes, Ref } from 'react';
import { Icon } from './Icon';
export function SearchField({
  className,
  inputClassName,
  inputRef,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & {
  inputClassName?: string;
  inputRef?: Ref<HTMLInputElement>;
}) {
  return (
    <label className={`${className ?? ''} search-field`}>
      <Icon name="search" strokeLinejoin={undefined} />
      <input ref={inputRef} className={inputClassName} type="search" {...props} />
    </label>
  );
}
