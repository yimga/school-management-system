import { Component, type ErrorInfo, type ReactNode } from "react";

export interface ErrorBoundaryProps {
  name: string;
  tenantId: string;
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

export class VizErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error(`[analytics:${this.props.name}] tenant=${this.props.tenantId}`, error, info);
  }

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="rmc-viz-error-fallback" role="alert">
          <strong>{this.props.name}</strong> could not be rendered for this tenant. Other
          dashboard panels remain available.
        </div>
      );
    }
    return this.props.children;
  }
}
