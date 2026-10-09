import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { PhonePair } from './components/PhonePair';
import './index.css';

// Lightweight route split (no router dependency): the phone-pairing page
// at /pair/<token> is a standalone mobile view — no header, no dashboard.
// Everything else renders the normal app.
const pairMatch = window.location.pathname.match(/^\/pair\/([^/]+)\/?$/);
const pairToken = pairMatch ? decodeURIComponent(pairMatch[1]) : null;

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    {pairToken ? <PhonePair token={pairToken} /> : <App />}
  </React.StrictMode>
);
