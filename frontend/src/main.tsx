import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import './styles/base.css';
import './styles/theme.css';
import './styles/app.css';
import './styles/table.css';
import './styles/recordings.css';
import './styles/processing.css';
import './styles/analysis.css';
import { App } from './app/App';
import { WorkspaceProvider } from './app/WorkspaceProvider';
import { normalizeLegacyRoute } from './app/useRoute';
import { createDemoWorkspace } from './data/demo-workspace';
import { createApiWorkspace } from './data/api-workspace';
import { createSyntheticWorkspace } from './data/synthetic-workspace';
import './styles/live-states.css';

normalizeLegacyRoute();
const params = new URLSearchParams(location.search);
const archiveMode =
  import.meta.env.DEV &&
  (import.meta.env.MODE === 'archive' ||
    params.get('workspace') === 'archive' ||
    params.get('synthetic') === '1');
if (archiveMode && params.has('synthetic')) {
  const url = new URL(location.href);
  url.searchParams.delete('synthetic');
  url.searchParams.set('workspace', 'archive');
  history.replaceState(null, '', url);
}
const service = archiveMode
  ? createSyntheticWorkspace()
  : import.meta.env.DEV && params.get('demo') === '1'
    ? createDemoWorkspace()
    : createApiWorkspace();
const root = createRoot(document.getElementById('app')!);
// Complete the initial shell and keyboard bindings before the module finishes.
flushSync(() =>
  root.render(
    <StrictMode>
      <WorkspaceProvider service={service}>
        <App />
      </WorkspaceProvider>
    </StrictMode>,
  ),
);
