import type {
  AllocationSlice,
  MetricKpiData,
  PulseTimeseriesPoint,
  TenantAnalyticsBundle,
  TrendDirection,
} from "../../components/shared/analytics/types";
import { roundMoney, sumMoney } from "../../components/shared/analytics/utils/chartGeometry";

/** Deterministic PRNG (mulberry32) keyed by tenant. */
export function createTenantRng(tenantId: string): () => number {
  let h = 1779033703;
  for (let i = 0; i < tenantId.length; i++) {
    h = Math.imul(h ^ tenantId.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  return () => {
    h = Math.imul(h ^ (h >>> 16), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    h ^= h >>> 16;
    return (h >>> 0) / 4294967296;
  };
}

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function isWeekend(d: Date): boolean {
  const day = d.getUTCDay();
  return day === 0 || day === 6;
}

/** Northern-hemisphere school break windows (approx.). */
function isBreakPeriod(d: Date): boolean {
  const m = d.getUTCMonth();
  const day = d.getUTCDate();
  if (m === 11 && day >= 18) return true;
  if (m === 0 && day <= 6) return true;
  if (m === 6 || m === 7) return true;
  return false;
}

function isTermStart(d: Date): boolean {
  const m = d.getUTCMonth();
  const day = d.getUTCDate();
  return (m === 8 && day <= 14) || (m === 0 && day >= 8 && day <= 21);
}

export interface SeedOptions {
  months?: number;
  startDate?: Date;
}

export function seedTenantAnalytics(
  tenantId: string,
  options: SeedOptions = {},
): TenantAnalyticsBundle {
  const months = options.months ?? 9;
  const start = options.startDate ?? new Date(Date.UTC(2025, 8, 1));
  const rng = createTenantRng(tenantId);
  const timeseries: PulseTimeseriesPoint[] = [];

  const cursor = new Date(start);
  const end = new Date(start);
  end.setUTCMonth(end.getUTCMonth() + months);

  while (cursor < end) {
    const weekend = isWeekend(cursor);
    const breakPeriod = isBreakPeriod(cursor);
    const termStart = isTermStart(cursor);

    const baseAttendance = 0.88 - (weekend ? 0.22 : 0) - (breakPeriod ? 0.35 : 0);
    const attendanceNoise = (rng() - 0.5) * 0.06;
    const attendanceRate = roundMoney(
      Math.min(99, Math.max(35, (baseAttendance + attendanceNoise) * 100)),
      1,
    );

    const baseRevenue = 4200 + (termStart ? 2800 : 0) - (weekend ? 900 : 0) - (breakPeriod ? 1100 : 0);
    const revenueNoise = (rng() - 0.5) * 400;
    const revenue = roundMoney(Math.max(250, baseRevenue + revenueNoise), 1);

    timeseries.push({
      date: isoDate(cursor),
      attendanceRate,
      revenue,
    });
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }

  const revenueTotal = sumMoney(timeseries.map((p) => p.revenue), 1);
  const attendanceAvg = roundMoney(
    timeseries.length
      ? timeseries.reduce((acc, p) => acc + p.attendanceRate, 0) / timeseries.length
      : 0,
    1,
  );

  const sparkAttendance = timeseries.slice(-14).map((p) => p.attendanceRate);
  const sparkRevenue = timeseries.slice(-14).map((p) => p.revenue);

  const allocationRaw = [
    { id: "instruction", label: "Instruction", weight: 0.42 },
    { id: "operations", label: "Operations", weight: 0.24 },
    { id: "facilities", label: "Facilities", weight: 0.18 },
    { id: "technology", label: "Technology", weight: 0.11 },
    { id: "reserve", label: "Reserve", weight: 0.05 },
  ];

  const budgetTotal = roundMoney(revenueTotal * 1.12, 1);
  const allocation: AllocationSlice[] = allocationRaw.map((row, i) => ({
    id: row.id,
    label: row.label,
    value: roundMoney(budgetTotal * row.weight, 1),
    dashPattern: i % 2 === 0 ? "0" : "4 3",
  }));

  const allocationSum = sumMoney(allocation.map((s) => s.value), 1);
  if (allocationSum !== budgetTotal && allocation.length) {
    const drift = roundMoney(budgetTotal - allocationSum, 1);
    allocation[0] = {
      ...allocation[0],
      value: roundMoney(allocation[0].value + drift, 1),
    };
  }

  const kpis: MetricKpiData[] = [
    buildKpi(
      "attendance",
      "Attendance rate",
      attendanceAvg,
      `${attendanceAvg.toFixed(1)}%`,
      sparkAttendance,
      tenantId,
      rng,
    ),
    buildKpi(
      "revenue",
      "Live revenue",
      revenueTotal,
      revenueTotal.toLocaleString(undefined, { maximumFractionDigits: 1 }),
      sparkRevenue,
      tenantId,
      rng,
    ),
    (() => {
      const enrolled = Math.round(820 + rng() * 120);
      return buildKpi(
        "enrollment",
        "Active students",
        enrolled,
        `${enrolled}`,
        sparkAttendance.map((v) => v * 8.2),
        tenantId,
        rng,
      );
    })(),
  ];

  return {
    tenantId,
    timeseries,
    kpis,
    allocation,
    totals: {
      revenue: revenueTotal,
      budget: budgetTotal,
    },
  };
}

function buildKpi(
  id: string,
  label: string,
  value: number,
  formattedValue: string,
  sparkline: number[],
  tenantId: string,
  rng: () => number,
): MetricKpiData {
  const deltaPercent = roundMoney((rng() - 0.35) * 12, 1);
  const direction: TrendDirection =
    deltaPercent > 0.4 ? "up" : deltaPercent < -0.4 ? "down" : "neutral";
  return {
    id,
    label,
    value,
    formattedValue,
    deltaPercent: Math.abs(deltaPercent),
    direction,
    sparkline,
    helpText: `${label} for tenant ${tenantId} — seeded deterministic curve.`,
  };
}

export function validateTenantAnalyticsIntegrity(bundle: TenantAnalyticsBundle): {
  ok: boolean;
  errors: string[];
} {
  const errors: string[] = [];
  const revenueFromSeries = sumMoney(bundle.timeseries.map((p) => p.revenue), 1);
  if (revenueFromSeries !== bundle.totals.revenue) {
    errors.push(
      `Revenue total mismatch: series=${revenueFromSeries} totals=${bundle.totals.revenue}`,
    );
  }
  const revenueKpi = bundle.kpis.find((k) => k.id === "revenue");
  if (revenueKpi && roundMoney(revenueKpi.value, 1) !== bundle.totals.revenue) {
    errors.push(`Revenue KPI does not match totals.revenue`);
  }
  const allocSum = sumMoney(bundle.allocation.map((s) => s.value), 1);
  if (allocSum !== bundle.totals.budget) {
    errors.push(`Allocation sum ${allocSum} != budget ${bundle.totals.budget}`);
  }
  return { ok: errors.length === 0, errors };
}
