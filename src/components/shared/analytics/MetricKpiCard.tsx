import { useId, useState } from "react";
import { PlatformIcon } from "./icons/PlatformIcon";
import { Sparkline } from "./Sparkline";
import type { MetricKpiData, TrendDirection } from "./types";
import { MetricKpiCardSkeleton } from "./skeletons/AnalyticsSkeletons";

export interface MetricKpiCardProps {
  tenantId: string;
  metric: MetricKpiData;
  loading?: boolean;
}

function deltaClass(direction: TrendDirection): string {
  if (direction === "up") return "rmc-viz-delta--up";
  if (direction === "down") return "rmc-viz-delta--down";
  return "rmc-viz-delta--neutral";
}

function deltaIcon(direction: TrendDirection): "trend-up" | "trend-down" | "trend-neutral" {
  if (direction === "up") return "trend-up";
  if (direction === "down") return "trend-down";
  return "trend-neutral";
}

export function MetricKpiCard({ tenantId, metric, loading = false }: MetricKpiCardProps) {
  const helpId = useId();
  const [helpOpen, setHelpOpen] = useState(false);

  if (loading) return <MetricKpiCardSkeleton />;

  const deltaLabel =
    metric.direction === "neutral"
      ? `${metric.deltaPercent.toFixed(1)}% no change`
      : `${metric.deltaPercent.toFixed(1)}% ${metric.direction}`;

  return (
    <article
      className="rmc-viz-card"
      data-tenant-id={tenantId}
      data-metric-id={metric.id}
      aria-labelledby={`${metric.id}-title`}
    >
      <header className="rmc-viz-card__header">
        <h3 id={`${metric.id}-title`} className="rmc-viz-card__title">
          {metric.label}
        </h3>
        <button
          type="button"
          className="rmc-viz-help-btn"
          aria-expanded={helpOpen}
          aria-controls={helpId}
          onClick={() => setHelpOpen((v) => !v)}
        >
          <PlatformIcon name="help" label={`About ${metric.label}`} size={16} strokeWidth={1.5} />
        </button>
      </header>
      <div className="rmc-viz-kpi__row">
        <p className="rmc-viz-kpi__value">{metric.formattedValue}</p>
        <Sparkline
          values={metric.sparkline}
          label={`${metric.label} trend for tenant ${tenantId}`}
        />
        <span className={`rmc-viz-delta ${deltaClass(metric.direction)}`}>
          <PlatformIcon
            name={deltaIcon(metric.direction)}
            label={deltaLabel}
            size={14}
            strokeWidth={2}
            aria-hidden
          />
          <span>{metric.deltaPercent.toFixed(1)}%</span>
        </span>
      </div>
      {helpOpen ? (
        <p id={helpId} className="rmc-viz-card__help" style={{ marginTop: "0.5rem", color: "var(--text-secondary)", fontSize: "var(--type-size-caption)" }}>
          {metric.helpText}
        </p>
      ) : null}
    </article>
  );
}
