import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  useSyncExternalStore,
  type Dispatch,
  type SetStateAction,
  type ReactNode,
} from 'react';
import type { WorkspaceService } from '../data/workspace-service';

const WorkspaceContext = createContext<WorkspaceService | null>(null);
const PresentationContext = createContext<Map<string, unknown> | null>(null);
export function WorkspaceProvider({
  service,
  children,
}: {
  service: WorkspaceService;
  children: ReactNode;
}) {
  const presentation = useRef(new Map<string, unknown>());
  return (
    <WorkspaceContext.Provider value={service}>
      <PresentationContext.Provider value={presentation.current}>
        {children}
      </PresentationContext.Provider>
    </WorkspaceContext.Provider>
  );
}
/** Session presentation state survives route unmounts; media and effects still stop. */
export function useRememberedState<T>(
  key: string,
  initial: T | (() => T),
): [T, Dispatch<SetStateAction<T>>] {
  const store = useContext(PresentationContext)!;
  const [value, update] = useState<T>(() =>
    store.has(key)
      ? (store.get(key) as T)
      : typeof initial === 'function'
        ? (initial as () => T)()
        : initial,
  );
  const current = useRef(value);
  const setValue = useCallback<Dispatch<SetStateAction<T>>>(
    (next) => {
      const result = typeof next === 'function' ? (next as (value: T) => T)(current.current) : next;
      current.current = result;
      store.set(key, result);
      update(result);
    },
    [key, store],
  );
  return [value, setValue];
}
export function useWorkspaceService() {
  const service = useContext(WorkspaceContext);
  if (!service) throw new Error('WorkspaceProvider is required.');
  return service;
}
export function useWorkspace() {
  const service = useWorkspaceService();
  return useSyncExternalStore(service.subscribe, service.getSnapshot);
}
