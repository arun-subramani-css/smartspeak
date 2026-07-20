import React, { useState } from 'react';
import { Header } from './components/Header';
import { VideoUploader } from './components/VideoUploader';
import { StatusTracker } from './components/StatusTracker';
import { Sparkles, ShieldCheck, Cpu, HardDrive } from 'lucide-react';

export default function App() {
  const [currentSessionId, setCurrentSessionId] = useState(null);

  const handleUploadSuccess = (sessionId) => {
    setCurrentSessionId(sessionId);
  };

  const handleReset = () => {
    setCurrentSessionId(null);
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg-app)' }}>
      <Header />
      
      <main className="max-w-screen" style={{ flex: 1, padding: '36px 24px 60px' }}>
        {/* Hero Section */}
        <div style={{ textAlign: 'center', maxWidth: '720px', margin: '0 auto 36px' }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '4px 14px',
            background: 'rgba(99, 102, 241, 0.12)',
            border: '1px solid rgba(99, 102, 241, 0.25)',
            borderRadius: '999px',
            fontSize: '0.8rem',
            color: 'var(--primary-400)',
            fontWeight: 600,
            marginBottom: '16px'
          }}>
            <Sparkles size={14} />
            <span>AI Public Speaking Coach — Video Preprocessing Pipeline</span>
          </div>

          <h1 style={{ fontSize: '2.4rem', fontWeight: 800, color: '#ffffff', lineHeight: 1.2, marginBottom: '12px' }}>
            Elevate Your Presentation Speaking Skills
          </h1>
          <p style={{ fontSize: '1rem', color: 'var(--text-secondary)', lineHeight: 1.6 }}>
            Upload your speech recording to safely stage the video, extract Whisper-ready 16kHz mono audio, and sample key posture frames.
          </p>
        </div>

        {/* System Specs Pill Bar */}
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          gap: '24px',
          margin: '0 auto 36px',
          padding: '12px 24px',
          background: 'var(--bg-surface)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '999px',
          maxWidth: '680px',
          fontSize: '0.82rem',
          color: 'var(--text-secondary)'
        }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Cpu size={15} color="var(--primary-400)" />
            <span>FastAPI + PyMongo</span>
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <ShieldCheck size={15} color="var(--accent-emerald)" />
            <span>FFmpeg 16kHz Mono WAV</span>
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <HardDrive size={15} color="var(--accent-cyan)" />
            <span>30-Day Auto Retention</span>
          </span>
        </div>

        {/* Main Interactive Workspace */}
        {!currentSessionId ? (
          <VideoUploader onUploadSuccess={handleUploadSuccess} />
        ) : (
          <StatusTracker sessionId={currentSessionId} onReset={handleReset} />
        )}
      </main>

      <footer style={{
        textAlign: 'center',
        padding: '24px',
        color: 'var(--text-tertiary)',
        fontSize: '0.8rem',
        borderTop: '1px solid var(--border-subtle)',
        background: 'rgba(11, 15, 23, 0.9)'
      }}>
        <div className="max-w-screen" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span>SmartSpeak Platform © 2026 — Enterprise AI Coach</span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--accent-emerald)' }}></span>
            <span>Module 1 (Upload) & Module 2 (Processing) Operational</span>
          </span>
        </div>
      </footer>
    </div>
  );
}
