import React from 'react';

/**
 * Top-level error boundary. If the React tree throws an unhandled error the UI
 * would otherwise go blank, leaving the motor running with no controls. This
 * boundary catches the crash and presents a minimal safe fallback with an
 * Emergency Stop button.
 */
export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error("Wavedriver UI crashed:", error, info.componentStack);
  }

  handleEstop = () => {
    try {
      window.pywebview?.api?.send_command("estop", { reason: "UI crashed — Emergency Stop" });
    } catch (_) {}
  };

  handleRetry = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary-screen">
          <div className="error-boundary-card">
            <h1 className="error-boundary-title">UI Error</h1>
            <p className="error-boundary-msg">
              The interface crashed unexpectedly.
              {this.state.error?.message && (
                <span className="error-boundary-detail"> ({this.state.error.message})</span>
              )}
            </p>
            <div className="error-boundary-actions">
              <button className="btn btn-danger btn-estop" onClick={this.handleEstop}>
                EMERGENCY STOP
              </button>
              <button className="btn btn-secondary" onClick={this.handleRetry}>
                Retry UI
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
