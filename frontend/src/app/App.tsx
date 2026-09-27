import { useEffect, useLayoutEffect, useState, type CSSProperties } from 'react';
import { useWorkspace, useWorkspaceService } from './WorkspaceProvider';
import { Sidebar } from './Sidebar';
import { SearchDialog } from './SearchDialog';
import { useRoute } from './useRoute';
import { RecordingsPage } from '../features/recordings/RecordingsPage';
import { ProcessingPage } from '../features/processing/ProcessingPage';
import { AnalysisPage } from '../features/analysis/AnalysisPage';
import { Icon } from '../components/Icon';
export function App() {
  const route = useRoute();
  const service = useWorkspaceService();
  const { error } = useWorkspace();
  useEffect(() => service.observe?.(route), [route, service]);
  const [search, setSearch] = useState(false);
  useEffect(() => {
    document.title = `${route[0].toUpperCase() + route.slice(1)} — Tectrace`;
  }, [route]);
  useLayoutEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if (document.querySelector('dialog[open]')) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        setSearch((current) => !current);
      }
    }
    window.addEventListener('keydown', shortcut);
    return () => window.removeEventListener('keydown', shortcut);
  }, []);
  return (
    <>
      <div
        className="group/sidebar-wrapper flex min-h-svh w-full has-data-[variant=inset]:bg-sidebar [--surface:var(--color-background)] dark:[--surface:color-mix(in_oklab,var(--color-sidebar)_60%,transparent)] dark:[--sidebar:var(--color-background)] [--sidebar-accent:color-mix(in_oklab,var(--color-sidebar-accent)_100%,var(--color-sidebar-accent-foreground)_4%)] dark:[--sidebar-accent:var(--color-card)] [--sidebar-animation-duration:200ms] [--sidebar-animation-ease:ease-[cubic-bezier(0.32,0.72,0,1)]] **:data-[slot=sidebar-gap]:duration-(--sidebar-animation-duration) **:data-[slot=sidebar-gap]:ease-(--sidebar-animation-ease)"
        data-slot="sidebar-wrapper"
        style={{ '--sidebar-width': '16rem', '--sidebar-width-icon': '2.25rem' } as CSSProperties}
      >
        <Sidebar route={route} />
        <main
          className="cn-sidebar-inset flex w-full flex-1 flex-col relative bg-(--surface) shadow-xs md:peer-data-[variant=inset]:peer-data-[state=collapsed]:ml-0"
          data-slot="sidebar-inset"
        >
          {error && (
            <div className="workspace-error inline-error" role="alert">
              <span>{error}</span>
              <button
                type="button"
                aria-label="Dismiss error"
                onClick={() => service.clearError?.()}
              >
                <Icon name="close" />
              </button>
            </div>
          )}
          {route === 'recordings' ? (
            <RecordingsPage />
          ) : route === 'processing' ? (
            <ProcessingPage />
          ) : (
            <AnalysisPage />
          )}
        </main>
      </div>
      {search && <SearchDialog onClose={() => setSearch(false)} />}
    </>
  );
}
