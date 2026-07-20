import React from 'react';
import { Mic, Activity, ExternalLink, ShieldCheck, Layers } from 'lucide-react';

export function Header() {
  return (
    <header style={{
      borderBottom: '1px solid var(--border-subtle)',
      background: 'rgba(11, 15, 23, 0.85)',
      backdropFilter: 'blur(16px)',
      position: 'sticky',
      top: 0,
      zIndex: 50,
      padding: '14px 0'
    }}>
      <div className="max-w-screen" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{
            background: 'linear-gradient(135deg, var(--primary-600), var(--accent-violet))',
            padding: '10px',
            borderRadius: '12px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 14px var(--primary-glow)'
          }}>
            <Mic size={22} color="#ffffff" />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h1 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#ffffff' }}>
                Smart<span style={{ color: 'var(--primary-400)' }}>Speak</span>
              </h1>
              <span style={{
                background: 'rgba(99, 102, 241, 0.15)',
                color: 'var(--primary-400)',
                border: '1px solid rgba(99, 102, 241, 0.3)',
                fontSize: '0.7rem',
                fontWeight: 700,
                padding: '2px 8px',
                borderRadius: '999px',
                textTransform: 'uppercase',
                letterSpacing: '0.05em'
              }}>
                Enterprise AI
              </span>
            </div>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
              Video Ingestion & Multimodal Preprocessing Engine
            </p>
          </div>
        </div>

        {/* Action Badges & API Docs Link */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '6px 12px',
            background: 'var(--bg-surface-elevated)',
            borderRadius: 'var(--radius-full)',
            border: '1px solid var(--border-subtle)',
            fontSize: '0.78rem',
            color: 'var(--text-secondary)'
          }}>
            <Activity size={14} color="var(--accent-emerald)" />
            <span>Pipeline Engine: <strong>Active</strong></span>
          </div>

          <a
            href="http://localhost:8000/docs"
            target="_blank"
            rel="noopener noreferrer"
            className="btn-secondary"
            style={{ textDecoration: 'none', padding: '6px 14px', fontSize: '0.8rem' }}
          >
            <span>API Docs</span>
            <ExternalLink size={14} />
          </a>
        </div>
      </div>
    </header>
  );
}
