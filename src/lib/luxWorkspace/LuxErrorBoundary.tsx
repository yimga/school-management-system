import React from "react";

export interface LuxErrorBoundaryProps {
  children: React.ReactNode;
  fallbackLabel?: string;
  onError?: (error: Error, info: React.ErrorInfo) => void;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class LuxErrorBoundary extends React.Component<LuxErrorBoundaryProps, State> {
  constructor(props: LuxErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    if (this.props.onError) this.props.onError(error, info);
    else if (typeof console !== "undefined") {
      console.error("[lux:error-boundary]", error, info);
    }
  }

  reset = (): void => {
    this.setState({ hasError: false, error: undefined });
  };

  render(): React.ReactNode {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="rmc-lux-error" role="alert" aria-live="assertive">
        <div className="rmc-lux-error__panel">
          <h3 className="rmc-lux-error__title">
            {this.props.fallbackLabel ?? "Workspace surface stalled"}
          </h3>
          <p className="rmc-lux-error__message">
            {this.state.error?.message ?? "An unexpected error occurred."}
          </p>
          <button
            type="button"
            className="rmc-lux-quick rmc-lux-quick--success"
            onClick={this.reset}
          >
            Retry
          </button>
        </div>
      </div>
    );
  }
}
