import { useCallback, useId, useMemo, useRef, useState } from "react";
import {
  buildAreaPath,
  buildSmoothPath,
  computeDomain,
  scaleLinear,
} from "./utils/chartGeometry";
import type { PulseTimeseriesPoint } from "./types";
import { PlatformPulseLineChartSkeleton } from "./skeletons/AnalyticsSkeletons";

export interface PlatformPulseLineChartProps {
  tenantId: string;
  data: PulseTimeseriesPoint[];
  loading?: boolean;
  width?: number;
  height?: number;
  title?: string;
}

interface TooltipState {
  x: number;
  y: number;
  point: PulseTimeseriesPoint;
}

const MARGIN = { top: 12, right: 48, bottom: 28, left: 44 };

export function PlatformPulseLineChart({
  tenantId,
  data,
  loading = false,
  width = 640,
  height = 220,
  title = "Campus pulse",
}: PlatformPulseLineChartProps) {
  const gradientId = useId().replace(/:/g, "");
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const chartW = width - MARGIN.left - MARGIN.right;
  const chartH = height - MARGIN.top - MARGIN.bottom;
  const baselineY = MARGIN.top + chartH;

  const { attendancePath, revenuePath, attendanceArea, revenueArea, points } = useMemo(() => {
    const clean = data.filter(
      (d) =>
        Number.isFinite(d.attendanceRate) &&
        Number.isFinite(d.revenue) &&
        d.date,
    );
    if (!clean.length) {
      return {
        attendancePath: "",
        revenuePath: "",
        attendanceArea: "",
        revenueArea: "",
        points: [] as Array<{
          px: number;
          attendanceY: number;
          revenueY: number;
          raw: PulseTimeseriesPoint;
        }>,
      };
    }

    const attendanceDomain = computeDomain(clean.map((d) => d.attendanceRate));
    const revenueDomain = computeDomain(clean.map((d) => d.revenue));

    const pts = clean.map((d, i) => {
      const px =
        MARGIN.left +
        (clean.length <= 1 ? chartW / 2 : (i / (clean.length - 1)) * chartW);
      const attendanceY = scaleLinear(
        d.attendanceRate,
        attendanceDomain,
        MARGIN.top,
        MARGIN.top + chartH,
      );
      const revenueY = scaleLinear(
        d.revenue,
        revenueDomain,
        MARGIN.top,
        MARGIN.top + chartH,
      );
      return { px, attendanceY, revenueY, raw: d };
    });

    const attendanceLine = buildSmoothPath(
      pts.map((p) => ({ x: p.px, y: p.attendanceY })),
    );
    const revenueLine = buildSmoothPath(
      pts.map((p) => ({ x: p.px, y: p.revenueY })),
    );

    const firstX = pts[0]?.px ?? MARGIN.left;
    const lastX = pts[pts.length - 1]?.px ?? MARGIN.left + chartW;

    return {
      attendancePath: attendanceLine,
      revenuePath: revenueLine,
      attendanceArea: buildAreaPath(attendanceLine, baselineY, firstX, lastX),
      revenueArea: buildAreaPath(revenueLine, baselineY, firstX, lastX),
      points: pts,
    };
  }, [data, chartW, chartH, baselineY]);

  const onPointerMove = useCallback(
    (event: React.PointerEvent<SVGSVGElement>) => {
      if (!points.length || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const localX = event.clientX - rect.left;
      let nearest = points[0];
      let minDist = Math.abs(nearest.px - localX);
      for (const p of points) {
        const dist = Math.abs(p.px - localX);
        if (dist < minDist) {
          minDist = dist;
          nearest = p;
        }
      }
      setTooltip({
        x: nearest.px,
        y: Math.min(nearest.attendanceY, nearest.revenueY) - 8,
        point: nearest.raw,
      });
    },
    [points],
  );

  if (loading) return <PlatformPulseLineChartSkeleton />;

  const hasInvalid = data.some(
    (d) => !Number.isFinite(d.attendanceRate) || !Number.isFinite(d.revenue),
  );
  if (hasInvalid) {
    throw new Error(`Invalid pulse timeseries for tenant ${tenantId}`);
  }

  return (
    <section
      className="rmc-viz-card rmc-viz-pulse chart-container"
      data-tenant-id={tenantId}
      aria-label={title}
    >
      <header className="rmc-viz-card__header">
        <h3 className="rmc-viz-card__title">{title}</h3>
        <span className="chart-legend chart-legend--muted">
          <span className="swatch" style={{ background: "var(--chart-color-1)" }} aria-hidden />
          Attendance
          <span
            className="swatch"
            style={{
              background: "var(--chart-color-4)",
              marginInlineStart: "0.75rem",
            }}
            aria-hidden
          />
          Revenue
        </span>
      </header>
      <div ref={containerRef} className="rmc-viz-pulse" style={{ minHeight: height }}>
        <svg
          width="100%"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label={`${title} for tenant ${tenantId}`}
          onPointerMove={onPointerMove}
          onPointerLeave={() => setTooltip(null)}
        >
          <defs>
            <linearGradient
              id={`${gradientId}-attendance`}
              x1="0"
              y1="0"
              x2="0"
              y2="1"
            >
              <stop offset="0%" stopColor="var(--chart-color-1)" stopOpacity="0.35" />
              <stop offset="100%" stopColor="var(--chart-color-1)" stopOpacity="0" />
            </linearGradient>
            <linearGradient id={`${gradientId}-revenue`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--chart-color-4)" stopOpacity="0.28" />
              <stop offset="100%" stopColor="var(--chart-color-4)" stopOpacity="0" />
            </linearGradient>
          </defs>
          <line
            className="chart-baseline"
            x1={MARGIN.left}
            x2={width - MARGIN.right}
            y1={baselineY}
            y2={baselineY}
          />
          {attendanceArea ? (
            <path
              className="rmc-viz-pulse__series--attendance"
              d={attendanceArea}
              fill={`url(#${gradientId}-attendance)`}
              stroke="none"
            />
          ) : null}
          {revenueArea ? (
            <path
              className="rmc-viz-pulse__series--revenue"
              d={revenueArea}
              fill={`url(#${gradientId}-revenue)`}
              stroke="none"
            />
          ) : null}
          {attendancePath ? (
            <path className="chart-line rmc-viz-pulse__series--attendance" d={attendancePath} fill="none" />
          ) : null}
          {revenuePath ? (
            <path className="chart-line rmc-viz-pulse__series--revenue" d={revenuePath} fill="none" />
          ) : null}
        </svg>
        {tooltip ? (
          <div
            className="rmc-viz-tooltip chart-tooltip"
            style={{
              left: `${(tooltip.x / width) * 100}%`,
              top: `${(tooltip.y / height) * 100}%`,
              transform: "translate(-50%, -100%)",
            }}
            role="status"
          >
            <div className="rmc-viz-tooltip__date">{tooltip.point.date}</div>
            <div>
              Attendance: <strong>{tooltip.point.attendanceRate.toFixed(1)}%</strong>
            </div>
            <div>
              Revenue: <strong>{tooltip.point.revenue.toFixed(1)}</strong>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
