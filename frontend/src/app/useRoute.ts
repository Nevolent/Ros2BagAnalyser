import { useSyncExternalStore } from 'react';
export type Route = 'recordings' | 'analysis' | 'processing';
const aliases: Record<string, string> = {
  '#/overview': '#/recordings',
  '#/workflows': '#/analysis',
  '#/analytics': '#/processing',
};
export function normalizeLegacyRoute() {
  if (aliases[location.hash]) history.replaceState(null, '', aliases[location.hash]);
}
const subscribe = (listener: () => void) => {
  window.addEventListener('hashchange', listener);
  return () => window.removeEventListener('hashchange', listener);
};
export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => location.hash);
  const normalized = aliases[hash] ?? hash;
  return normalized === '#/analysis' || normalized.startsWith('#/analysis/')
    ? 'analysis'
    : normalized === '#/processing'
      ? 'processing'
      : 'recordings';
}

export function useRecordingId(): string {
  const hash = useSyncExternalStore(subscribe, () => location.hash);
  return hash.startsWith('#/analysis/') ? hash.slice('#/analysis/'.length) : '';
}
