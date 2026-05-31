/* KPI variety pack — 6 distinct visualization primitives so dashboards
 * don't all show the same sparkline 12 times.  Each primitive accepts
 * the same VizCommon props for consistency.
 */

import React from "react";

export type VizTone = "neutral" | "good" | "warn" | "danger";

const TONE_STROKE: Record<VizTone, string> = {
  neutral: "var(--lux-text-secondary)",
  good: "var(--lux-accent-emerald)",
  warn: "var(--lux-accent-amber)",
  danger: "var(--lux-accent-rose)",
};

const TONE_FILL: Record<VizTone, string> = {
  neutral: "var(--lux-canvas-elev-2)",
  good: "var(--lux-accent-emerald-soft)",
  warn: "var(--lux-accent-amber-soft)",
  danger: "var(--lux-accent-rose-soft)",
};

export interface SparklineProps {
  values: number[];
  tone?: VizTone;
  width?: number;
  height?: number;
  label?: string;
}

export function Sparkline({ values, tone = "neutral", width = 96, height = 28, label }: SparklineProps) {
  if (values.length === 0) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = width / Math.max(1, values.length - 1);
  const points = values
    .map((v, i) => `${i * step},${height - ((v - min) / span) * height}`)
    .join(" ");
  const last = values[values.length - 1];
  const lastY = height - ((last - min) / span) * height;
  return (
    <svg
      className="rmc-lux-viz-sparkline"
      width={width}
      height={height}
      role="img"
      aria-label={label ?? "trend sparkline"}
    >
      <polyline
        fill="none"
        stroke={TONE_STROKE[tone]}
        strokeWidth={1.6}
        strokeLinejoin="round"
        strokeLinecap="round"
        points={points}
      />
      <circle cx={(values.length - 1) * step} cy={lastY} r={2.4} fill={TONE_STROKE[tone]} />
    </svg>
  );
}

export interface DeltaChipProps {
  pct: number;
  tone?: VizTone;
  ariaLabel?: string;
}

export function DeltaChip({ pct, tone, ariaLabel }: DeltaChipProps) {
  const resolvedTone: VizTone = tone ?? (pct >= 5 ? "good" : pct <= -5 ? "danger" : "neutral");
  const sign = pct > 0 ? "▲" : pct < 0 ? "▼" : "·";
  return (
    <span
      className={`rmc-lux-viz-delta rmc-lux-viz-delta--${resolvedTone}`}
      aria-label={ariaLabel ?? `change ${pct.toFixed(1)} percent`}
    >
      <span aria-hidden="true">{sign}</span>
      <span>{Math.abs(pct).toFixed(1)}%</span>
    </span>
  );
}

export interface DonutProps {
  value: number;
  max?: number;
  tone?: VizTone;
  size?: number;
  thickness?: number;
  label?: string;
  showCenter?: boolean;
}

export function Donut({
  value,
  max = 100,
  tone = "good",
  size = 56,
  thickness = 6,
  label,
  showCenter = true,
}: DonutProps) {
  const safeMax = Math.max(1, max);
  const safeVal = Math.max(0, Math.min(value, safeMax));
  const radius = (size - thickness) / 2;
  const circ = 2 * Math.PI * radius;
  const offset = circ * (1 - safeVal / safeMax);
  return (
    <div
      className={`rmc-lux-viz-donut rmc-lux-viz-donut--${tone}`}
      style={{ width: size, height: size }}
      role="img"
      aria-label={label ?? `${Math.round((safeVal / safeMax) * 100)} percent`}
    >
      <svg width={size} height={size}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--lux-border-thin)"
          strokeWidth={thickness}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={TONE_STROKE[tone]}
          strokeWidth={thickness}
          strokeLinecap="round"
          strokeDasharray={circ}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      {showCenter ? (
        <span className="rmc-lux-viz-donut__center">
          {Math.round((safeVal / safeMax) * 100)}%
        </span>
      ) : null}
    </div>
  );
}

export interface BarStackProps {
  bars: { label: string; value: number; tone?: VizTone }[];
  max?: number;
  height?: number;
}

export function BarStack({ bars, max, height = 80 }: BarStackProps) {
  if (bars.length === 0) return null;
  const ceiling = max ?? Math.max(...bars.map((b) => b.value), 1);
  return (
    <div
      className="rmc-lux-viz-bars"
      role="img"
      aria-label={`bar chart of ${bars.length} values`}
      style={{ height }}
    >
      {bars.map((bar, idx) => {
        const tone = bar.tone ?? "neutral";
        const h = Math.max(2, (bar.value / ceiling) * height);
        return (
          <span
            key={`${bar.label}-${idx}`}
            className={`rmc-lux-viz-bar rmc-lux-viz-bar--${tone}`}
            style={{ height: h, backgroundColor: TONE_FILL[tone], borderColor: TONE_STROKE[tone] }}
            title={`${bar.label}: ${bar.value}`}
          >
            <span className="rmc-lux-viz-bar__label">{bar.label}</span>
          </span>
        );
      })}
    </div>
  );
}

export interface GaugeProps {
  value: number;
  min?: number;
  max?: number;
  tone?: VizTone;
  label?: string;
}

export function Gauge({ value, min = 0, max = 100, tone = "good", label }: GaugeProps) {
  const span = Math.max(1, max - min);
  const pct = Math.max(0, Math.min(1, (value - min) / span));
  const angle = -90 + pct * 180;
  return (
    <div
      className={`rmc-lux-viz-gauge rmc-lux-viz-gauge--${tone}`}
      role="img"
      aria-label={label ?? `gauge value ${value}`}
    >
      <svg width={80} height={50} viewBox="0 0 80 50">
        <path d="M 8 42 A 32 32 0 0 1 72 42" stroke="var(--lux-border-thin)" strokeWidth={4} fill="none" strokeLinecap="round" />
        <path
          d="M 8 42 A 32 32 0 0 1 72 42"
          stroke={TONE_STROKE[tone]}
          strokeWidth={4}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={100.5}
          strokeDashoffset={100.5 * (1 - pct)}
        />
        <line
          x1={40}
          y1={42}
          x2={40}
          y2={14}
          stroke={TONE_STROKE[tone]}
          strokeWidth={1.5}
          transform={`rotate(${angle} 40 42)`}
        />
        <circle cx={40} cy={42} r={2.5} fill={TONE_STROKE[tone]} />
      </svg>
    </div>
  );
}

export interface HeatStripProps {
  cells: number[];
  max?: number;
  tone?: VizTone;
  label?: string;
}

export function HeatStrip({ cells, max, tone = "good", label }: HeatStripProps) {
  if (cells.length === 0) return null;
  const ceiling = max ?? Math.max(...cells, 1);
  return (
    <div
      className={`rmc-lux-viz-heat rmc-lux-viz-heat--${tone}`}
      role="img"
      aria-label={label ?? `heat strip of ${cells.length} values`}
    >
      {cells.map((value, idx) => {
        const alpha = Math.max(0.08, Math.min(0.95, value / ceiling));
        const stroke = TONE_STROKE[tone];
        return (
          <span
            key={idx}
            className="rmc-lux-viz-heat__cell"
            style={{ backgroundColor: stroke, opacity: alpha }}
            title={`${value}`}
          />
        );
      })}
    </div>
  );
}

export interface KpiCardProps {
  label: string;
  value: React.ReactNode;
  viz?: React.ReactNode;
  delta?: React.ReactNode;
  hint?: string;
  tone?: VizTone;
  href?: string;
  onClick?: () => void;
}

export function KpiCard({ label, value, viz, delta, hint, tone = "neutral", href, onClick }: KpiCardProps) {
  const Tag = href ? "a" : "div";
  return (
    <Tag
      href={href as never}
      onClick={onClick}
      className={`rmc-lux-kpi rmc-lux-kpi--${tone}` + (href || onClick ? " is-actionable" : "")}
    >
      <div className="rmc-lux-kpi__head">
        <span className="rmc-lux-kpi__label">{label}</span>
        {delta ?? null}
      </div>
      <div className="rmc-lux-kpi__body">
        <span className="rmc-lux-kpi__value">{value}</span>
        {viz ? <span className="rmc-lux-kpi__viz">{viz}</span> : null}
      </div>
      {hint ? <p className="rmc-lux-kpi__hint">{hint}</p> : null}
    </Tag>
  );
}
