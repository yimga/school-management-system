import type { AnalyticsVizOverviewResponse, TenantAnalyticsBundle } from "../../components/shared/analytics/types";
import {
  seedTenantAnalytics,
  validateTenantAnalyticsIntegrity,
} from "../../database/seeds/analytics-seeder";

export interface FetchTenantBundleOptions {
  tenantId: string;
  apiUrl?: string;
  from?: string;
  to?: string;
  compare?: boolean;
  /** Force client seeder (tests / corruptRevenue). */
  useSeeder?: boolean;
  corruptRevenue?: boolean;
}

export async function fetchTenantBundle(
  options: FetchTenantBundleOptions,
): Promise<TenantAnalyticsBundle> {
  const { tenantId, apiUrl, from, to, compare, useSeeder, corruptRevenue } = options;

  let bundle: TenantAnalyticsBundle;

  if (!useSeeder && apiUrl) {
    const params = new URLSearchParams({ tenant: tenantId });
    if (from) params.set("from", from);
    if (to) params.set("to", to);
    if (compare) params.set("compare", "1");
    const res = await fetch(`${apiUrl}?${params.toString()}`, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (!res.ok) {
      throw new Error(`analytics overview ${res.status}`);
    }
    const payload = (await res.json()) as AnalyticsVizOverviewResponse;
    bundle = payload.bundle;
  } else {
    bundle = seedTenantAnalytics(tenantId);
    const check = validateTenantAnalyticsIntegrity(bundle);
    if (!check.ok) {
      throw new Error(check.errors.join("; "));
    }
  }

  if (corruptRevenue) {
    return {
      ...bundle,
      timeseries: bundle.timeseries.map((p) => ({
        ...p,
        revenue: Number.NaN,
      })),
    };
  }
  return bundle;
}

export function exportBundleCsv(bundle: TenantAnalyticsBundle): string {
  const header = "date,attendanceRate,revenue";
  const rows = bundle.timeseries.map(
    (p) => `${p.date},${p.attendanceRate},${p.revenue}`,
  );
  return [header, ...rows].join("\n");
}

export function downloadTextFile(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function exportChartPng(svgSelector: string, filename: string): Promise<void> {
  const svg =
    document.querySelector<SVGSVGElement>(svgSelector) ||
    document.querySelector<SVGSVGElement>(`${svgSelector} svg`) ||
    document.querySelector<SVGSVGElement>(`${svgSelector.replace(".chart-line", "")} svg`);
  if (!svg) return;
  const xml = new XMLSerializer().serializeToString(svg);
  const img = new Image();
  const url = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(xml)}`;
  await new Promise<void>((resolve, reject) => {
    img.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = svg.viewBox.baseVal.width || svg.clientWidth || 640;
      canvas.height = svg.viewBox.baseVal.height || svg.clientHeight || 200;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        reject(new Error("canvas"));
        return;
      }
      ctx.fillStyle = "transparent";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0);
      canvas.toBlob((blob) => {
        if (!blob) {
          reject(new Error("blob"));
          return;
        }
        const pngUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = pngUrl;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(pngUrl);
        resolve();
      }, "image/png");
    };
    img.onerror = () => reject(new Error("svg"));
    img.src = url;
  });
}
