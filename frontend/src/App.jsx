import React, { useState } from 'react';
import { Header } from './components/Header';
import { VideoUploader } from './components/VideoUploader';
import { StatusTracker } from './components/StatusTracker';

export default function App() {
  const [currentSessionId, setCurrentSessionId] = useState(null);

  const handleUploadSuccess = (sessionId) => {
    setCurrentSessionId(sessionId);
  };

  const handleReset = () => {
    setCurrentSessionId(null);
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Header />
      
      <main className="container" style={{ flex: 1, padding: '40px 20px' }}>
        {!currentSessionId ? (
          <VideoUploader onUploadSuccess={handleUploadSuccess} />
        ) : (
          <StatusTracker sessionId={currentSessionId} onReset={handleReset} />
        )}
      </main>

      <footer style={{
        textAlign: 'center',
        padding: '20px',
        color: 'var(--text-muted)',
        fontSize: '0.8rem',
        borderTop: '1px solid var(--border-color)'
      }}>
        SmartSpeak © 2026 — AI Public Speaking Coach (Module 1 & 2)
      </footer>
    </div>
  );
}
