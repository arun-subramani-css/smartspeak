import React from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

/**
 * ErrorBoundary — catches render-time errors anywhere below it and shows a
 * friendly fallback instead of a blank white screen. Errors are logged to
 * the console so they remain debuggable.
 */
export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error('SmartSpeak crashed while rendering:', error, info);
  }

  handleReload = () => {
    this.setState({ error: null });
    window.location.reload();
  };

  render() {
    if (this.state.error) {
      return (
        <main className="max-w-container" style={{ padding: '64px 24px', textAlign: 'center' }}>
          <div className="pro-card" style={{ maxWidth: 520, margin: '0 auto', padding: '40px 32px' }}>
            <div style={{
              width: 56, height: 56, borderRadius: '50%',
              background: '#fef2f2', color: '#dc2626',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 16px',
            }}>
              <AlertTriangle size={28} />
            </div>
            <h1 style={{ fontSize: '1.25rem', fontWeight: 800, marginBottom: 8 }}>
              Something went wrong
            </h1>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: 4 }}>
              The app hit an unexpected error while displaying this page.
            </p>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: 20 }}>
              Your uploaded videos and past reports are safe.
            </p>
            <button className="btn-purple" onClick={this.handleReload}>
              <RefreshCw size={16} />
              <span>Reload SmartSpeak</span>
            </button>
            {import.meta.env.DEV && (
              <pre style={{
                marginTop: 20, padding: 12, textAlign: 'left',
                background: 'var(--bg-subtle)', border: '1px solid var(--border-subtle)',
                borderRadius: 8, fontSize: '0.72rem', color: '#b91c1c',
                maxHeight: 160, overflow: 'auto', whiteSpace: 'pre-wrap',
              }}>
                {String(this.state.error?.message || this.state.error)}
              </pre>
            )}
          </div>
        </main>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
