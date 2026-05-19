import { useId, useMemo, useState } from "react";
import { describeDonutArc, roundMoney, sumMoney } from "./utils/chartGeometry";
import type { AllocationSlice } from "./types";
import { ResourceAllocationDonutSkeleton } from "./skeletons/AnalyticsSkeletons";

export interface ResourceAllocationDonutProps {
  tenantId: string;
  slices: AllocationSlice[];
  loading?: boolean;
  size?: number;
  title?: string;
}

const SLICE_COLORS = [
  "var(--chart-color-1)",
  "var(--chart-color-4)",
  "var(--chart-color-5)",
  "var(--chart-color-6)",
  "var(--chart-color-2)",
];

export function ResourceAllocationDonut({
  tenantId,
  slices,
  loading = false,
  size = 180,
  title = "Resource allocation",
}: ResourceAllocationDonutProps) {
  const labelId = useId();
  const [activeId, setActiveId] = useState<string | null>(null);

  const { arcs, total, centerLabel } = useMemo(() => {
    const clean = slices.filter((s) => Number.isFinite(s.value) && s.value >= 0);
    const totalValue = sumMoney(clean.map((s) => s.value), 1);
    if (totalValue <= 0) {
      return { arcs: [], total: 0, centerLabel: "0.0" };
    }
    const cx = size / 2;
    const cy = size / 2;
    const outerR = size * 0.42;
    const innerR = size * 0.28;
    let cursor = -Math.PI / 2;
    const built = clean.map((slice, index) => {
      const fraction = slice.value / totalValue;
      const sweep = fraction * Math.PI * 2;
      const start = cursor;
      const end = cursor + sweep;
      cursor = end;
      return {
        slice,
        d: describeDonutArc(cx, cy, outerR, innerR, start, end),
        color: SLICE_COLORS[index % SLICE_COLORS.length],
        percent: roundMoney(fraction * 100, 1),
      };
    });
    const active = activeId ? built.find((a) => a.slice.id === activeId) : null;
    return {
      arcs: built,
      total: totalValue,
      centerLabel: active
        ? `${active.percent}%`
        : totalValue.toLocaleString(undefined, { maximumFractionDigits: 1 }),
    };
  }, [slices, size, activeId]);

  if (loading) return <ResourceAllocationDonutSkeleton />;

  return (
    <section
      className="rmc-viz-card"
      data-tenant-id={tenantId}
      aria-labelledby={labelId}
    >
      <header className="rmc-viz-card__header">
        <h3 id={labelId} className="rmc-viz-card__title">
          {title}
        </h3>
      </header>
      <div className="rmc-viz-donut chart-container">
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          role="img"
          aria-label={`${title} donut chart for tenant ${tenantId}`}
        >
          <title>{title}</title>
          {arcs.map(({ slice, d, color }) => (
            <path
              key={slice.id}
              d={d}
              fill={color}
              stroke="var(--surface-elevated)"
              strokeWidth={1}
              strokeDasharray={slice.dashPattern}
              opacity={activeId && activeId !== slice.id ? 0.55 : 1}
              tabIndex={0}
              role="graphics-symbol"
              aria-label={`${slice.label}: ${slice.value}`}
              onFocus={() => setActiveId(slice.id)}
              onBlur={() => setActiveId(null)}
              onMouseEnter={() => setActiveId(slice.id)}
              onMouseLeave={() => setActiveId(null)}
            />
          ))}
          <text
            x="50%"
            y="46%"
            textAnchor="middle"
            className="rmc-viz-donut__center-label"
          >
            Total budget
          </text>
          <text
            x="50%"
            y="56%"
            textAnchor="middle"
            className="rmc-viz-donut__center-value"
          >
            {centerLabel}
          </text>
        </svg>
        <ul className="rmc-viz-donut__legend" aria-label="Allocation breakdown">
          {arcs.map(({ slice, color, percent }) => (
            <li key={slice.id} className="rmc-viz-donut__legend-item">
              <span
                className="rmc-viz-donut__swatch"
                style={{ background: color, borderStyle: "dashed", borderWidth: 1, borderColor: "var(--hairline)" }}
                aria-hidden
              />
              <span>
                {slice.label} — {slice.value.toFixed(1)} ({percent}%)
              </span>
            </li>
          ))}
        </ul>
      </div>
      <p className="visually-hidden">
        Total allocated: {total.toFixed(1)} for tenant {tenantId}
      </p>
    </section>
  );
}
