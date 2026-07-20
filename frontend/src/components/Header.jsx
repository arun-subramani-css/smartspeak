import React from 'react';
import { Mic } from 'lucide-react';

export function Header() {
  return (
    <header style={{
      background: '#ffffff',
      borderBottom: '1px solid #f1f5f9',
      padding: '18px 0'
    }}>
      <div className="max-w-container" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            background: 'var(--primary-purple)',
            width: '38px',
            height: '38px',
            borderRadius: '10px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#ffffff'
          }}>
            <Mic size={20} />
          </div>
          <span style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.03em' }}>
            SmartSpeak
          </span>
        </div>

        {/* Active Status Badge */}
        <div className="badge-active" style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8rem', fontWeight: 600 }}>
          <span style={{ width: '7px', height: '7px', borderRadius: '50%', background: '#10b981' }}></span>
          <span>Active</span>
        </div>
      </div>
    </header>
  );
}
