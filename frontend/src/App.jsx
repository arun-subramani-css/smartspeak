import React, { useEffect, useState } from 'react';
import { Header } from './components/Header';
import { VideoUploader } from './components/VideoUploader';
import { StatusTracker } from './components/StatusTracker';
import { RecentReports } from './components/RecentReports';
import { ScoreTrendChart } from './components/ScoreTrendChart';
import { SessionCompare } from './components/SessionCompare';
import { ErrorBoundary } from './components/ErrorBoundary';
import { Sparkles, Check } from 'lucide-react';

export default function App() {
  // Persist the active session across refreshes so an in-progress upload
  // isn't lost when the tab reloads.
  const [currentSessionId, setCurrentSessionId] = useState(
    () => localStorage.getItem('smartspeak.activeSession') || null
  );
  // Side-by-side comparison pair {olderId, newerId}, set from Recent Reports.
  const [comparePair, setComparePair] = useState(null);

  useEffect(() => {
    if (currentSessionId) {
      localStorage.setItem('smartspeak.activeSession', currentSessionId);
    } else {
      localStorage.removeItem('smartspeak.activeSession');
    }
  }, [currentSessionId]);

  // Opening any session is a navigation: any stale comparison is left behind.
  const openSession = (sessionId) => {
    setComparePair(null);
    setCurrentSessionId(sessionId);
  };

  const handleUploadSuccess = (sessionId) => {
    openSession(sessionId);
  };

  const handleReset = () => {
    setComparePair(null);
    setCurrentSessionId(null);
  };

  // From a report: compare it against the previous completed session.
  // Loads the history list on demand to find the prior session id, then
  // switches to the landing view where the comparison renders.
  const handleCompareWithPrevious = async () => {
    try {
      const res = await fetch('/api/v1/sessions/history?limit=25&completed_only=true');
      if (!res.ok) return;
      const data = await res.json();
      const list = data.sessions || [];
      const idx = list.findIndex((s) => s.session_id === currentSessionId);
      if (idx >= 0 && idx + 1 < list.length) {
        setComparePair({ olderId: list[idx + 1].session_id, newerId: currentSessionId });
        setCurrentSessionId(null); // exit the report so the compare view shows
      }
    } catch {
      /* history unavailable — silently skip */
    }
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <a href="#main-content" className="skip-link">Skip to content</a>
      <Header />

      <main id="main-content" className="max-w-container" style={{ flex: 1, padding: '48px 24px 64px', width: '100%' }}>
        <ErrorBoundary>
        {!currentSessionId ? (
          <>
            {/* Hero Section */}
            <div className="animate-fade-in" style={{ textAlign: 'center', maxWidth: '720px', margin: '0 auto 40px' }}>
              {/* Badge */}
              <div style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '5px 14px',
                background: 'var(--primary-purple-light)',
                border: '1px solid var(--primary-purple-border)',
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
                fontSize: 'clamp(2rem, 5vw, 2.75rem)',
                fontWeight: 800,
                color: 'var(--text-primary)',
                lineHeight: 1.15,
                letterSpacing: '-0.03em',
                marginBottom: '16px'
              }}>
                Elevate your <span style={{
                  background: 'linear-gradient(120deg, #7c3aed 0%, #4f46e5 60%, #2563eb 100%)',
                  WebkitBackgroundClip: 'text',
                  backgroundClip: 'text',
                  color: 'transparent'
                }}>speaking skills</span>.
              </h1>

              {/* Subtitle */}
              <p style={{
                fontSize: '1.05rem',
                color: 'var(--text-secondary)',
                lineHeight: 1.6,
                marginBottom: '24px'
              }}>
                Upload a recording of your speech and get a full coaching report in minutes — pacing,
                filler words, pauses, eye contact, posture, and gestures, analyzed together.
              </p>

              {/* Checkmarks */}
              <div style={{
                display: 'flex',
                justifyContent: 'center',
                gap: '24px',
                fontSize: '0.875rem',
                fontWeight: 600,
                color: 'var(--text-secondary)',
                flexWrap: 'wrap'
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
                  Videos never leave your machine
                </span>
              </div>
            </div>

            {/* Ingestion Card / Status Tracker */}
            {comparePair && (
              <SessionCompare
                olderId={comparePair.olderId}
                newerId={comparePair.newerId}
                onOpenSession={openSession}
                onClose={() => setComparePair(null)}
              />
            )}
            <VideoUploader onUploadSuccess={handleUploadSuccess} />
            <RecentReports
              onOpenSession={openSession}
              onCompareSession={(id, prevId) => setComparePair({ olderId: prevId, newerId: id })}
            />
            <ScoreTrendChart />
          </>
        ) : (
          <StatusTracker
            sessionId={currentSessionId}
            onReset={handleReset}
            onCompareWithPrevious={handleCompareWithPrevious}
          />
        )}
        </ErrorBoundary>
      </main>

      {/* Footer */}
      <footer className="app-footer" style={{
        background: '#ffffff',
        borderTop: '1px solid #f1f5f9',
        padding: '24px 0',
        color: '#64748b',
        fontSize: '0.8125rem'
      }}>
        <div className="max-w-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '8px' }}>
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
