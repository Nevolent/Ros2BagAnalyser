import type { SVGProps } from 'react';
const paths = {
  search: 'm16 16 4 4',
  close: 'm4 4 8 8m0-8-8 8',
  chevron: 'm6 9 6 6 6-6',
  earlier: 'm5 12 7-7 7 7M12 19V5',
  later: 'm5 12 7 7 7-7M12 5v14',
  cancel: 'm6 6 12 12M6 18 18 6',
  retry: 'M3 10a9 9 0 1 1 2.5 8M3 4v6h6',
  pause: 'M9 5v14M15 5v14',
  play: 'm8 5 11 7-11 7Z',
  folder: 'M20 20H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h5l2 2h9a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2Z',
};
export type IconName = keyof typeof paths;
export function Icon({ name, ...props }: SVGProps<SVGSVGElement> & { name: IconName }) {
  return (
    <svg
      viewBox={name === 'close' ? '0 0 16 16' : '0 0 24 24'}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {name === 'search' && <circle cx="10.5" cy="10.5" r="6.5" />}
      <path d={paths[name]} />
    </svg>
  );
}
