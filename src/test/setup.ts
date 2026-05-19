import "@testing-library/jest-dom/vitest";
import "../../static/css/rmc-analytics-viz.css";

/** Minimal design tokens for chart contrast in jsdom. */
const style = document.createElement("style");
style.textContent = `
  :root {
    --text-primary: #1d1d1f;
    --text-secondary: #424245;
    --text-tertiary: #6e6e73;
    --surface-elevated: #ffffff;
    --surface-sunken: #ebebef;
    --hairline: rgba(0,0,0,0.08);
    --chart-color-1: #4f46e5;
    --chart-color-4: #0ea5e9;
    --chart-color-5: #22c55e;
    --chart-color-6: #f59e0b;
    --chart-color-2: #a5b4fc;
    --school-primary: #4f46e5;
    --ds-success: #16a34a;
    --ds-danger: #ef4444;
    --ds-success-bg: rgba(22,163,74,0.12);
    --ds-danger-bg: rgba(239,68,68,0.12);
    --chart-tooltip-bg: #ffffff;
    --chart-tooltip-border: rgba(0,0,0,0.08);
    --chart-tooltip-shadow: 0 4px 12px rgba(0,0,0,0.08);
    --chart-tooltip-text: #1d1d1f;
    --chart-tooltip-muted: #6e6e73;
    --material-blur: blur(12px);
    --type-size-caption: 0.8125rem;
    --type-size-eyebrow: 0.72rem;
    --type-size-headline-m: 1.5rem;
    --type-size-title-m: 1.25rem;
    --radius-md: 12px;
    --radius-sm: 8px;
    --motion-fast: 150ms ease;
  }
`;
document.head.appendChild(style);
