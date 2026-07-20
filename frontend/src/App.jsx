import React, { useState } from 'react';
import { Header } from './components/Header';
import { VideoUploader } from './components/VideoUploader';
import { StatusTracker } from './components/StatusTracker';
import { Sparkles, Check } from 'lucide-react';

export default function App() {
  const [currentSessionId, setCurrentSessionId] = useState(null);

  const handleUploadSuccess = (sessionId) => {
    setCurrentSessionId(sessionId);
  };

  const handleReset = () => {
    setCurrentSessionId(null);
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: '#ffffff' }}>
      <Header />
      
      <main className="max-w-container" style={{ flex: 1, padding: '48px 24px 64px' }}>
        {/* Hero Section */}
        <div style={{ textAlign: 'center', maxWidth: '680px', margin: '0 auto 40px' }}>
          {/* Badge */}
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '5px 14px',
            background: 'var(--primary-purple-light)',
            borderRadius: '999px',
            fontSize: '0.75rem',
            color: 'var(--primary-purple)',
            fontWeight: 700,
            letterSpacing: '0.05em',
            textTransform: 'uppercase',
            marginBottom: '20px'
          }}>
            <Sparkles size={14} />
            <span>AI Public Speaking Coach</span>
          </div>

          {/* Heading */}
          <h1 style={{
            fontSize: '2.5rem',
            fontWeight: 800,
            color: 'var(--text-primary)',
            lineHeight: 1.15,
            letterSpacing: '-0.03em',
            marginBottom: '16px'
          }}>
            Elevate your speaking skills.
          </h1>

          {/* Subtitle */}
          <p style={{
            fontSize: '1.05rem',
            color: 'var(--text-secondary)',
            lineHeight: 1.6,
            marginBottom: '24px'
          }}>
            Upload your speech recording to stage the video, extract Whisper-ready audio, and sample key posture frames for intelligent analysis.
          </p>

          {/* Checkmarks */}
          <div style={{
            display: 'flex',
            justifyContent: 'center',
            gap: '24px',
            fontSize: '0.875rem',
            fontWeight: 600,
            color: 'var(--text-secondary)'
          }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Check size={16} color="var(--primary-purple)" strokeWidth={3} />
              High-fidelity analysis
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Check size={16} color="var(--primary-purple)" strokeWidth={3} />
              30-Day Auto Retention
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <Check size={16} color="var(--primary-purple)" strokeWidth={3} />
              GDPR Compliant
            </span>
          </div>
        </div>

        {/* Ingestion Card / Status Tracker */}
        {!currentSessionId ? (
          <VideoUploader onUploadSuccess={handleUploadSuccess} />
        ) : (
          <StatusTracker sessionId={currentSessionId} onReset={handleReset} />
        )}
      </main>

      {/* Footer */}
      <footer style={{
        background: '#ffffff',
        borderTop: '1px solid #f1f5f9',
        padding: '24px 0',
        color: '#64748b',
        fontSize: '0.8125rem'
      }}>
        <div className="max-w-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
            <span>© 2026 SmartSpeak Platform</span>
            <a href="#" style={{ color: '#64748b', textDecoration: 'none' }}>Terms</a>
            <a href="#" style={{ color: '#64748b', textDecoration: 'none' }}>Privacy</a>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '7px', height: '7px', borderRadius: '50%', background: '#10b981' }}></span>
            <span>System Status: Operational</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
