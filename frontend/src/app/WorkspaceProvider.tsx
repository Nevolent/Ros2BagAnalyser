import { createContext, useContext, useSyncExternalStore, type ReactNode } from 'react';
import type { WorkspaceService } from '../data/workspace-service';

const WorkspaceContext = createContext<WorkspaceService | null>(null);
export function WorkspaceProvider({
  service,
  children,
}: {
  service: WorkspaceService;
  children: ReactNode;
}) {
  return <WorkspaceContext.Provider value={service}>{children}</WorkspaceContext.Provider>;
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
