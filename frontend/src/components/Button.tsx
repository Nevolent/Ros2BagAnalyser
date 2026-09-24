import type { ComponentPropsWithRef } from 'react';
export function Button({
  className = '',
  size = 'default',
  ...props
}: ComponentPropsWithRef<'button'> & { size?: 'default' | 'icon' }) {
  return (
    <button
      type="button"
      className={`cn-button group/button inline-flex shrink-0 select-none items-center justify-center whitespace-nowrap outline-none transition-all disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 cn-button-variant-secondary cn-button-size-${size} ${className}`}
      data-size={size}
      data-slot="button"
      data-variant="secondary"
      {...props}
    />
  );
}
