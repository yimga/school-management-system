export interface PulseTimeseriesPoint {
  date: string;
  attendanceRate: number;
  revenue: number;
}

export type TrendDirection = "up" | "down" | "neutral";

export interface MetricKpiData {
  id: string;
  label: string;
  value: number;
  formattedValue: string;
  deltaPercent: number;
  direction: TrendDirection;
  sparkline: number[];
  helpText: string;
}

export interface AllocationSlice {
  id: string;
  label: string;
  value: number;
  /** Distinct dash pattern for non-color differentiation (WCAG). */
  dashPattern: string;
}

export interface TenantAnalyticsBundleMeta {
  empty?: boolean;
  message?: string;
  source?: string;
  compare?: boolean;
  from?: string;
  to?: string;
  generatedAt?: string;
}

export interface TenantAnalyticsBundle {
  tenantId: string;
  timeseries: PulseTimeseriesPoint[];
  kpis: MetricKpiData[];
  allocation: AllocationSlice[];
  totals: {
    revenue: number;
    budget: number;
  };
  meta?: TenantAnalyticsBundleMeta;
  drillDown?: Record<string, string>;
}

export interface AnalyticsVizOverviewResponse {
  bundle: TenantAnalyticsBundle;
  api?: string;
}
