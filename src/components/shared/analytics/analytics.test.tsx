import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TenantOverview } from "../../../apps/dashboard/TenantOverview";
import {
  buildSmoothPath,
  computeDomain,
  scaleLinear,
} from "./utils/chartGeometry";
import { PlatformPulseLineChart } from "./PlatformPulseLineChart";
import { MetricKpiCard } from "./MetricKpiCard";
import { ResourceAllocationDonut } from "./ResourceAllocationDonut";
import {
  seedTenantAnalytics,
  validateTenantAnalyticsIntegrity,
} from "../../../database/seeds/analytics-seeder";

describe("chart geometry hydration", () => {
  it("builds finite paths from mock tenant dataset", () => {
    const bundle = seedTenantAnalytics("tenant-alpha");
    const domain = computeDomain(bundle.timeseries.map((p) => p.attendanceRate));
    const points = bundle.timeseries.map((p, i) => ({
      x: i * 10,
      y: scaleLinear(p.attendanceRate, domain, 100, 10),
    }));
    const path = buildSmoothPath(points);
    expect(path).toMatch(/^M /);
    expect(path).not.toMatch(/NaN/);
    expect(Number.isFinite(domain.min)).toBe(true);
    expect(Number.isFinite(domain.max)).toBe(true);
  });

  it("renders pulse chart without throw", () => {
    const bundle = seedTenantAnalytics("tenant-beta");
    const { container } = render(
      <PlatformPulseLineChart
        tenantId="tenant-beta"
        data={bundle.timeseries}
        loading={false}
        width={480}
        height={200}
      />,
    );
    expect(container.querySelector("path.chart-line")).toBeTruthy();
  });
});

describe("viewport responsiveness", () => {
  it("scales chart viewBox on narrow width", () => {
    const bundle = seedTenantAnalytics("tenant-gamma");
    const { container } = render(
      <PlatformPulseLineChart
        tenantId="tenant-gamma"
        data={bundle.timeseries.slice(0, 30)}
        width={320}
        height={180}
      />,
    );
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("viewBox")).toBe("0 0 320 180");
    expect(getComputedStyle(svg!).display).toBe("block");
  });

  it("wraps KPI row on mobile container", () => {
    const bundle = seedTenantAnalytics("tenant-delta");
    const metric = bundle.kpis[0];
    const { container } = render(
      <div style={{ width: "320px" }}>
        <MetricKpiCard tenantId="tenant-delta" metric={metric} />
      </div>,
    );
    const row = container.querySelector(".rmc-viz-kpi__row");
    expect(row).toBeTruthy();
    expect(getComputedStyle(row!).flexWrap).toBe("wrap");
  });
});

describe("analytics seeder integrity", () => {
  it("populates aligned financial totals per tenant", () => {
    const a = seedTenantAnalytics("school-100");
    const b = seedTenantAnalytics("school-100");
    const c = seedTenantAnalytics("school-200");

    expect(validateTenantAnalyticsIntegrity(a).ok).toBe(true);
    expect(a).toEqual(b);
    expect(c.tenantId).toBe("school-200");
    expect(c.totals.revenue).not.toBe(a.totals.revenue);

    const revenueSum = a.timeseries.reduce((acc, p) => acc + p.revenue, 0);
    expect(Math.round(revenueSum * 10) / 10).toBe(a.totals.revenue);
  });

  it("renders donut slices that sum to budget total", () => {
    const bundle = seedTenantAnalytics("school-finance");
    render(
      <ResourceAllocationDonut tenantId={bundle.tenantId} slices={bundle.allocation} />,
    );
    expect(screen.getByText(/Total budget/i)).toBeTruthy();
    const sliceSum = bundle.allocation.reduce((acc, s) => acc + s.value, 0);
    expect(Math.round(sliceSum * 10) / 10).toBe(bundle.totals.budget);
  });
});

describe("error boundary isolation", () => {
  it("keeps KPI cards visible when pulse data is corrupt", async () => {
    render(
      <TenantOverview
        tenantId="corrupt-tenant"
        simulateAsync={false}
        corruptRevenue
        useSeeder
      />,
    );
    expect(await screen.findByText(/Tenant overview/i)).toBeTruthy();
    expect(screen.getByRole("heading", { name: /Attendance rate/i })).toBeTruthy();
    expect(screen.getByText(/could not be rendered/i)).toBeTruthy();
  });
});

describe("theme transition stability", () => {
  it("keeps readable KPI values when theme attribute toggles", () => {
    const bundle = seedTenantAnalytics("tenant-theme");
    document.documentElement.setAttribute("data-theme", "dark");
    const { container, rerender } = render(
      <MetricKpiCard tenantId="tenant-theme" metric={bundle.kpis[0]} />,
    );
    const valueColor = getComputedStyle(container.querySelector(".rmc-viz-kpi__value")!).color;
    document.documentElement.setAttribute("data-theme", "light");
    rerender(<MetricKpiCard tenantId="tenant-theme" metric={bundle.kpis[0]} />);
    const valueColorLight = getComputedStyle(
      container.querySelector(".rmc-viz-kpi__value")!,
    ).color;
    expect(valueColor).toBeTruthy();
    expect(valueColorLight).toBeTruthy();
  });
});
