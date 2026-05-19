import { Component, type ErrorInfo, type ReactNode } from "react";

export interface ErrorBoundaryProps {
  name: string;
  tenantId: string;
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  retryKey: number;
}

export class VizErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, retryKey: 0 };

  static getDerivedStateFromError(): Partial<ErrorBoundaryState> {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`[analytics:${this.props.name}] tenant=${this.props.tenantId}`, error, info);
  }

  private handleRetry = (): void => {
    this.setState((prev) => ({
      hasError: false,
      retryKey: prev.retryKey + 1,
    }));
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="rmc-viz-error-fallback" role="alert" data-dashboard-error-boundary="1">
          <strong>{this.props.name}</strong> could not be rendered for this tenant. Other
          dashboard panels remain available.
          <div className="rmc-viz-error-fallback__actions">
            <button
              type="button"
              className="btn btn-sm btn-outline-primary"
              onClick={this.handleRetry}
            >
              Retry connection
            </button>
          </div>
        </div>
      );
    }
    return <div key={this.state.retryKey}>{this.props.children}</div>;
  }
}

/** Alias for sovereign dual-dashboard topology prompt contract. */
export const DashboardErrorBoundary = VizErrorBoundary;
