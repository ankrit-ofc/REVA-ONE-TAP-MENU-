/**
 * Top-level error boundary. If any render throws, show a recoverable message with
 * a reload button instead of a silent blank white page (important for a POS in the
 * middle of service). Also logs the error so it's visible in the console.
 */
import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error('Unhandled render error:', error, info.componentStack)
  }

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children

    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '1rem',
          padding: '1.5rem',
          textAlign: 'center',
          fontFamily: 'system-ui, -apple-system, sans-serif',
          color: '#1e293b',
        }}
      >
        <div style={{ fontSize: '2.5rem' }}>😕</div>
        <h1 style={{ fontSize: '1.1rem', margin: 0 }}>Something went wrong</h1>
        <p style={{ fontSize: '0.9rem', color: '#64748b', margin: 0, maxWidth: '22rem' }}>
          The app hit an unexpected error. Reloading usually fixes it.
        </p>
        <button
          onClick={() => window.location.reload()}
          style={{
            padding: '0.6rem 1.25rem',
            background: '#1b4332',
            color: '#fff',
            border: 'none',
            borderRadius: '0.6rem',
            fontSize: '0.95rem',
            fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          Reload
        </button>
      </div>
    )
  }
}
