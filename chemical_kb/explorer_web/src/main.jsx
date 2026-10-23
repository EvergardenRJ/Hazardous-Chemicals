import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './app/AppShell.jsx';
import './styles.css';
import './refresh.css';
import './theme/workspace.css';
import './theme/layout-details.css';
import './theme/portal.css';
import './theme/refinement.css';
import { UIProvider } from './components/WorkspaceUI';

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <UIProvider><App /></UIProvider>
  </React.StrictMode>
);
