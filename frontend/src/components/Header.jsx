import React from 'react';
import { Mic } from 'lucide-react';

export function Header() {
  return (
    <header className="app-header" style={{
      background: 'rgba(255, 255, 255, 0.85)',
      backdropFilter: 'blur(10px)',
      borderBottom: '1px solid #f1f5f9',
      padding: '16px 0',
      position: 'sticky',
      top: 0,
      zIndex: 100
    }}>
      <div className="max-w-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        {/* Brand */}
        <a href="/" onClick={(e) => { e.preventDefault(); window.location.reload(); }}
          style={{ display: 'flex', alignItems: 'center', gap: '12px', textDecoration: 'none', cursor: 'pointer' }}
          aria-label="SmartSpeak home — reload to start over">
          <div style={{
            background: 'linear-gradient(135deg, #7c3aed 0%, #8b5cf6 100%)',
            width: '38px',
            height: '38px',
            borderRadius: '10px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#ffffff',
            boxShadow: '0 4px 12px rgba(124, 58, 237, 0.3)'
          }}>
            <Mic size={20} />
          </div>
          <span style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.03em' }}>
            SmartSpeak
          </span>
        </a>

        {/* Active Status Badge */}
        <div className="badge-active no-print" style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', fontWeight: 600 }}>
          <span className="animate-pulse-soft" style={{ width: '7px', height: '7px', borderRadius: '50%', background: '#10b981' }}></span>
          <span>Active</span>
        </div>
      </div>
    </header>
  );
}

export default Header;
