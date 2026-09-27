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
import './styles/scroll-area.css';
import { App } from './app/App';
import { WorkspaceProvider } from './app/WorkspaceProvider';
import { normalizeLegacyRoute } from './app/useRoute';
import { createDemoWorkspace } from './data/demo-workspace';
import { createApiWorkspace } from './data/api-workspace';
import { createSyntheticWorkspace } from './data/synthetic-workspace';
import './styles/live-states.css';

normalizeLegacyRoute();
const params = new URLSearchParams(location.search);
const syntheticMode = params.get('synthetic') === '1' || params.get('workspace') === 'archive';
const service = syntheticMode
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
