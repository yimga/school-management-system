import { Component, type ErrorInfo, type ReactNode } from "react";

export interface SupportErrorBoundaryProps {
  surface?: string;
  children: ReactNode;
}

interface SupportErrorBoundaryState {
  hasError: boolean;
  retryKey: number;
}

export class SupportErrorBoundary extends Component<
  SupportErrorBoundaryProps,
  SupportErrorBoundaryState
> {
  state: SupportErrorBoundaryState = { hasError: false, retryKey: 0 };

  static getDerivedStateFromError(): Partial<SupportErrorBoundaryState> {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(
      `[support:${this.props.surface || "help"}]`,
      error,
      info.componentStack,
    );
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
        <div
          className="alert alert-warning small mb-0"
          role="alert"
          data-rmc-support-error-boundary-fallback="1"
        >
          <strong>Help assistant unavailable.</strong> Use the article body below or open a
          support request.
          <div className="mt-2">
            <button type="button" className="btn btn-sm btn-outline-secondary" onClick={this.handleRetry}>
              Retry
            </button>
          </div>
        </div>
      );
    }
    return <div key={this.state.retryKey}>{this.props.children}</div>;
  }
}
