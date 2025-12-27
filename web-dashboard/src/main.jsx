import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, Routes, Route } from 'react-router';
import { ThemeProvider } from 'styled-components';
import { theme } from '@mrrobot/cast-component-library';
import App from './App';
import AlertsPage from './pages/AlertsPage';
import InvestigatePage from './pages/InvestigatePage';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ThemeProvider theme={theme}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<App />}>
            <Route index element={<AlertsPage />} />
            <Route path="alerts" element={<AlertsPage />} />
            <Route path="investigate/:incidentId" element={<InvestigatePage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  </React.StrictMode>
);
