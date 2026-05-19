import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchTenantBundle } from "./fetchTenantBundle";

describe("fetchTenantBundle", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses client seeder when useSeeder is true", async () => {
    const bundle = await fetchTenantBundle({
      tenantId: "audit-tenant",
      useSeeder: true,
    });
    expect(bundle.tenantId).toBe("audit-tenant");
    expect(bundle.timeseries.length).toBeGreaterThan(0);
  });

  it("fetches overview JSON from apiUrl", async () => {
    const payload = {
      bundle: {
        tenantId: "live-school",
        timeseries: [{ date: "2026-01-01", attendanceRate: 90, revenue: 100 }],
        kpis: [],
        allocation: [],
        totals: { revenue: 100, budget: 112 },
        meta: { source: "live" },
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => payload,
      }),
    );
    const bundle = await fetchTenantBundle({
      tenantId: "live-school",
      apiUrl: "/api/internal/analytics-viz/overview/",
      from: "2026-01-01",
      to: "2026-01-31",
      compare: true,
    });
    expect(bundle.tenantId).toBe("live-school");
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("tenant=live-school"),
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls[0][0]).toContain("compare=1");
  });
});
