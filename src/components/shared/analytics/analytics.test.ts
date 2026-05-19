/**
 * Phase 5 — geometry + seeder integrity (no JSX; complements analytics.test.tsx).
 */
import { describe, expect, it } from "vitest";
import {
  buildSmoothPath,
  computeDomain,
  roundMoney,
  scaleLinear,
  sumMoney,
} from "./utils/chartGeometry";
import {
  seedTenantAnalytics,
  validateTenantAnalyticsIntegrity,
} from "../../../database/seeds/analytics-seeder";

describe("analytics seeder CLI contract", () => {
  it("seeds deterministic multi-month curves per tenant", () => {
    const bundle = seedTenantAnalytics("cli-tenant-1", { months: 6 });
    expect(bundle.timeseries.length).toBeGreaterThan(150);
    expect(validateTenantAnalyticsIntegrity(bundle).ok).toBe(true);
  });

  it("applies weekend and break attendance patterns", () => {
    const bundle = seedTenantAnalytics("pattern-tenant", {
      months: 4,
      startDate: new Date(Date.UTC(2025, 8, 1)),
    });
    const weekend = bundle.timeseries.filter((p) => {
      const d = new Date(`${p.date}T12:00:00Z`);
      return d.getUTCDay() === 0 || d.getUTCDay() === 6;
    });
    const weekday = bundle.timeseries.filter((p) => {
      const d = new Date(`${p.date}T12:00:00Z`);
      const day = d.getUTCDay();
      return day >= 1 && day <= 5;
    });
    expect(weekend.length).toBeGreaterThan(0);
    expect(weekday.length).toBeGreaterThan(0);
    const weekendAvg =
      weekend.reduce((a, p) => a + p.attendanceRate, 0) / weekend.length;
    const weekdayAvg =
      weekday.reduce((a, p) => a + p.attendanceRate, 0) / weekday.length;
    expect(weekendAvg).toBeLessThan(weekdayAvg);
  });

  it("aligns financial totals to one decimal across relations", () => {
    const bundle = seedTenantAnalytics("finance-tenant");
    const seriesTotal = sumMoney(bundle.timeseries.map((p) => p.revenue), 1);
    expect(seriesTotal).toBe(bundle.totals.revenue);
    const allocTotal = sumMoney(bundle.allocation.map((s) => s.value), 1);
    expect(allocTotal).toBe(bundle.totals.budget);
    const revenueKpi = bundle.kpis.find((k) => k.id === "revenue");
    expect(roundMoney(revenueKpi?.value ?? 0, 1)).toBe(bundle.totals.revenue);
  });
});

describe("chart path geometry", () => {
  it("never emits NaN in smooth paths", () => {
    const domain = computeDomain([10, 50, 30, 80]);
    const points = [0, 1, 2, 3].map((i) => ({
      x: i * 20,
      y: scaleLinear([10, 50, 30, 80][i], domain, 100, 0),
    }));
    const path = buildSmoothPath(points);
    expect(path).not.toMatch(/NaN/);
  });
});
