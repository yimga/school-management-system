import { buildSmoothPath, computeDomain, scaleLinear } from "./utils/chartGeometry";

export interface SparklineProps {
  values: number[];
  width?: number;
  height?: number;
  className?: string;
  /** Accessible summary for screen readers. */
  label: string;
}

export function Sparkline({
  values,
  width = 80,
  height = 24,
  className = "",
  label,
}: SparklineProps) {
  const clean = values.filter((v) => Number.isFinite(v));
  const domain = computeDomain(clean.length ? clean : [0]);
  const padX = 2;
  const padY = 2;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;

  const points = clean.map((v, i) => ({
    x: padX + (clean.length <= 1 ? innerW / 2 : (i / (clean.length - 1)) * innerW),
    y: scaleLinear(v, domain, padY, padY + innerH),
  }));

  const linePath = buildSmoothPath(points, 0.2);
  const areaPath =
    linePath && points.length
      ? `${linePath} L ${points[points.length - 1].x} ${height - padY} L ${points[0].x} ${height - padY} Z`
      : "";

  return (
    <svg
      className={`rmc-sparkline ${className}`.trim()}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={label}
    >
      <title>{label}</title>
      {areaPath ? <path className="chart-area" d={areaPath} /> : null}
      {linePath ? <path className="chart-line" d={linePath} /> : null}
    </svg>
  );
}
