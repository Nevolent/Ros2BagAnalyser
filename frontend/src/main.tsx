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
import './styles/live-states.css';

normalizeLegacyRoute();
const service =
  import.meta.env.DEV && new URLSearchParams(location.search).get('demo') === '1'
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
