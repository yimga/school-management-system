import { useCallback, useEffect, useMemo, useState } from "react";
import {
  MetricKpiCard,
  PlatformPulseLineChart,
  ResourceAllocationDonut,
} from "../../components/shared/analytics";
import type { TenantAnalyticsBundle } from "../../components/shared/analytics/types";
import { VizErrorBoundary } from "./ErrorBoundary";
import {
  downloadTextFile,
  exportBundleCsv,
  exportChartPng,
  fetchTenantBundle,
} from "./fetchTenantBundle";

export interface TenantOverviewProps {
  tenantId: string;
  apiUrl?: string;
  /** Simulates edge API latency when true. */
  simulateAsync?: boolean;
  /** Inject corrupt revenue series to prove error isolation. */
  corruptRevenue?: boolean;
  /** Skip API and use client seeder. */
  useSeeder?: boolean;
}

function defaultFromDate(): string {
  const d = new Date();
  d.setDate(d.getDate() - 90);
  return d.toISOString().slice(0, 10);
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function TenantOverview({
  tenantId,
  apiUrl,
  simulateAsync = false,
  corruptRevenue = false,
  useSeeder = false,
}: TenantOverviewProps) {
  const [loading, setLoading] = useState(true);
  const [bundle, setBundle] = useState<TenantAnalyticsBundle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [from, setFrom] = useState(defaultFromDate);
  const [to, setTo] = useState(todayIso);
  const [compare, setCompare] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    if (simulateAsync) {
      await new Promise((r) => setTimeout(r, 120));
    }
    try {
      const data = await fetchTenantBundle({
        tenantId,
        apiUrl,
        from,
        to,
        compare,
        useSeeder,
        corruptRevenue,
      });
      setBundle(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "load failed");
      setBundle(null);
    } finally {
      setLoading(false);
    }
  }, [tenantId, apiUrl, from, to, compare, useSeeder, corruptRevenue, simulateAsync]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const chartWidth = useMemo(() => {
    if (typeof window === "undefined") return 640;
    return Math.min(960, Math.max(320, window.innerWidth - 48));
  }, []);

  const empty = bundle?.meta?.empty && !loading;

  return (
    <div className="rmc-viz-root" data-tenant-id={tenantId}>
      <header style={{ marginBottom: "1rem" }}>
        <h2
          style={{
            margin: 0,
            fontSize: "var(--type-size-title-m, 1.25rem)",
            color: "var(--text-primary)",
          }}
        >
          Tenant overview
        </h2>
        <p
          style={{
            margin: "0.25rem 0 0",
            color: "var(--text-secondary)",
            fontSize: "var(--type-size-caption)",
          }}
        >
          Isolated analytics for <strong>{tenantId}</strong>
          {bundle?.meta?.source ? ` · ${bundle.meta.source}` : ""}
        </p>
      </header>

      <div
        className="rmc-viz-toolbar"
        role="toolbar"
        aria-label="Analytics controls"
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "0.5rem",
          marginBottom: "1rem",
          alignItems: "center",
        }}
      >
        <label style={{ color: "var(--text-secondary)", fontSize: "var(--type-size-caption)" }}>
          From{" "}
          <input
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            aria-label="From date"
          />
        </label>
        <label style={{ color: "var(--text-secondary)", fontSize: "var(--type-size-caption)" }}>
          To{" "}
          <input type="date" value={to} onChange={(e) => setTo(e.target.value)} aria-label="To date" />
        </label>
        <label style={{ color: "var(--text-secondary)", fontSize: "var(--type-size-caption)" }}>
          <input
            type="checkbox"
            checked={compare}
            onChange={(e) => setCompare(e.target.checked)}
          />{" "}
          Compare prior period
        </label>
        <button
          type="button"
          className="btn btn-sm btn-outline-secondary"
          onClick={() => setRefreshKey((k) => k + 1)}
        >
          Refresh
        </button>
        <button
          type="button"
          className="btn btn-sm btn-outline-secondary"
          disabled={!bundle}
          onClick={() =>
            bundle &&
            downloadTextFile(`${tenantId}-analytics.csv`, exportBundleCsv(bundle), "text/csv")
          }
        >
          Export CSV
        </button>
        <button
          type="button"
          className="btn btn-sm btn-outline-secondary"
          disabled={loading}
          onClick={() =>
            void exportChartPng(
              `[data-tenant-id="${tenantId}"] .rmc-viz-pulse svg`,
              `${tenantId}-pulse.png`,
            )
          }
        >
          Export chart PNG
        </button>
      </div>

      {error ? (
        <p role="alert" style={{ color: "var(--ds-danger, #dc3545)" }}>
          {error}
        </p>
      ) : null}

      {empty ? (
        <p className="rmc-viz-empty" style={{ color: "var(--text-secondary)" }}>
          {bundle?.meta?.message || "No data in this range."}
        </p>
      ) : null}

      <div className="rmc-viz-tenant-grid">
        {(["attendance", "revenue", "enrollment"] as const).map((id) => {
          const metric = bundle?.kpis.find((k) => k.id === id);
          const drill = bundle?.drillDown?.[id];
          return (
            <VizErrorBoundary key={id} name={`KPI:${id}`} tenantId={tenantId}>
              <div>
                <MetricKpiCard
                  tenantId={tenantId}
                  metric={
                    metric ?? {
                      id,
                      label: id,
                      value: 0,
                      formattedValue: "—",
                      deltaPercent: 0,
                      direction: "neutral",
                      sparkline: [],
                      helpText: "",
                    }
                  }
                  loading={loading || !metric}
                />
                {drill && !loading ? (
                  <a
                    href={drill}
                    className="rmc-viz-drill-link"
                    style={{
                      fontSize: "var(--type-size-caption)",
                      color: "var(--text-secondary)",
                    }}
                  >
                    View details
                  </a>
                ) : null}
              </div>
            </VizErrorBoundary>
          );
        })}

        <div className="rmc-viz-tenant-grid__wide">
          <VizErrorBoundary name="Campus pulse" tenantId={tenantId}>
            <PlatformPulseLineChart
              tenantId={tenantId}
              data={bundle?.timeseries ?? []}
              loading={loading}
              width={chartWidth}
            />
          </VizErrorBoundary>
        </div>

        <div className="rmc-viz-tenant-grid__wide">
          <VizErrorBoundary name="Resource allocation" tenantId={tenantId}>
            <ResourceAllocationDonut
              tenantId={tenantId}
              slices={bundle?.allocation ?? []}
              loading={loading}
            />
          </VizErrorBoundary>
        </div>
      </div>
    </div>
  );
}
