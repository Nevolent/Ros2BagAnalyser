import { useLayoutEffect, useRef, type InputHTMLAttributes } from 'react';
export function Checkbox({
  indeterminate = false,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { indeterminate?: boolean }) {
  const ref = useRef<HTMLInputElement>(null);
  useLayoutEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate;
  }, [indeterminate]);
  return (
    <label className="bag-select">
      <input ref={ref} className="bag-checkbox" type="checkbox" {...props} />
    </label>
  );
}
