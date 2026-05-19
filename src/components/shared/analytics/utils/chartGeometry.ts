/** Pure geometry helpers — no DOM, no NaN leakage. */

export interface Point2 {
  x: number;
  y: number;
}

export interface SeriesScale {
  min: number;
  max: number;
}

export function finiteOr(value: number, fallback: number): number {
  return Number.isFinite(value) ? value : fallback;
}

export function scaleLinear(
  value: number,
  domain: SeriesScale,
  rangeMin: number,
  rangeMax: number,
): number {
  const v = finiteOr(value, domain.min);
  const span = domain.max - domain.min || 1;
  const t = (v - domain.min) / span;
  return rangeMax - t * (rangeMax - rangeMin);
}

export function computeDomain(values: number[], padRatio = 0.08): SeriesScale {
  const clean = values.filter((n) => Number.isFinite(n));
  if (clean.length === 0) return { min: 0, max: 1 };
  let min = Math.min(...clean);
  let max = Math.max(...clean);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const pad = (max - min) * padRatio;
  return { min: min - pad, max: max + pad };
}

export function buildSmoothPath(
  points: Point2[],
  tension = 0.35,
): string {
  if (points.length === 0) return "";
  if (points.length === 1) {
    const p = points[0];
    return `M ${p.x} ${p.y}`;
  }
  const d: string[] = [`M ${points[0].x} ${points[0].y}`];
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] ?? points[i];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2] ?? p2;
    const cp1x = p1.x + ((p2.x - p0.x) * tension) / 6;
    const cp1y = p1.y + ((p2.y - p0.y) * tension) / 6;
    const cp2x = p2.x - ((p3.x - p1.x) * tension) / 6;
    const cp2y = p2.y - ((p3.y - p1.y) * tension) / 6;
    d.push(`C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${p2.x} ${p2.y}`);
  }
  return d.join(" ");
}

export function buildAreaPath(linePath: string, baselineY: number, firstX: number, lastX: number): string {
  if (!linePath) return "";
  return `${linePath} L ${lastX} ${baselineY} L ${firstX} ${baselineY} Z`;
}

export function polarToCartesian(
  cx: number,
  cy: number,
  radius: number,
  angleRad: number,
): Point2 {
  return {
    x: cx + radius * Math.cos(angleRad),
    y: cy + radius * Math.sin(angleRad),
  };
}

export function describeDonutArc(
  cx: number,
  cy: number,
  outerR: number,
  innerR: number,
  startAngle: number,
  endAngle: number,
): string {
  const startOuter = polarToCartesian(cx, cy, outerR, startAngle);
  const endOuter = polarToCartesian(cx, cy, outerR, endAngle);
  const startInner = polarToCartesian(cx, cy, innerR, endAngle);
  const endInner = polarToCartesian(cx, cy, innerR, startAngle);
  const largeArc = endAngle - startAngle > Math.PI ? 1 : 0;
  return [
    `M ${startOuter.x} ${startOuter.y}`,
    `A ${outerR} ${outerR} 0 ${largeArc} 1 ${endOuter.x} ${endOuter.y}`,
    `L ${startInner.x} ${startInner.y}`,
    `A ${innerR} ${innerR} 0 ${largeArc} 0 ${endInner.x} ${endInner.y}`,
    "Z",
  ].join(" ");
}

export function roundMoney(value: number, decimals = 1): number {
  const factor = 10 ** decimals;
  return Math.round(value * factor) / factor;
}

export function sumMoney(values: number[], decimals = 1): number {
  const raw = values.reduce((acc, v) => acc + (Number.isFinite(v) ? v : 0), 0);
  return roundMoney(raw, decimals);
}
