/**
 * v3.37.0 — vitest coverage for ``lib/tenant_switcher.ts``.
 *
 * 12 tests:
 *   1. Round-trip: addTenant + getKnownTenants returns the same row.
 *   2. Duplicate slug rejection (throws typed error).
 *   3. activeSlug defaults to FIRST tenant on first-add.
 *   4. Subsequent adds preserve existing activeSlug.
 *   5. setActiveTenant: known slug updates state.
 *   6. setActiveTenant: unknown slug is a no-op (does NOT corrupt).
 *   7. removeTenant: removing the active row resets activeSlug to next.
 *   8. removeTenant: removing the last row resets activeSlug to null.
 *   9. formatFingerprintForDisplay: 4-char hex grouping works.
 *  10. formatFingerprintForDisplay: empty + invalid b64 fallbacks.
 *  11. fetchAndRecordPubkey: triggers re-fetch with ?tenant=<slug>,
 *      records the returned fingerprint into storage.
 *  12. Empty-tenants edge case: getKnownTenants on virgin storage.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  addTenant,
  EMPTY_STATE,
  fetchAndRecordPubkey,
  formatFingerprintForDisplay,
  getKnownTenants,
  markVerified,
  recordFingerprint,
  removeTenant,
  setActiveTenant,
  setStorageBackend,
} from "../src/lib/tenant_switcher";
import type { LocalStorageAreaLike } from "../src/lib/tenant_switcher";

/** In-memory chrome.storage.local fake. */
function makeFakeStorage(): LocalStorageAreaLike & {
  _data: Record<string, unknown>;
} {
  const data: Record<string, unknown> = {};
  return {
    _data: data,
    async get(keys) {
      if (typeof keys === "string") {
        return keys in data ? { [keys]: data[keys] } : {};
      }
      if (Array.isArray(keys)) {
        const out: Record<string, unknown> = {};
        for (const k of keys) {
          if (k in data) out[k] = data[k];
        }
        return out;
      }
      // object form: defaults
      const out: Record<string, unknown> = {};
      for (const k of Object.keys(keys)) {
        out[k] = k in data ? data[k] : (keys as Record<string, unknown>)[k];
      }
      return out;
    },
    async set(items) {
      for (const k of Object.keys(items)) {
        data[k] = items[k];
      }
    },
  };
}

beforeEach(() => {
  setStorageBackend(makeFakeStorage());
});

afterEach(() => {
  setStorageBackend(null);
});

describe("tenant_switcher storage round-trips", () => {
  it("addTenant + getKnownTenants round-trips the row", async () => {
    await addTenant("alpha", "Alpha Academy");
    const state = await getKnownTenants();
    expect(state.tenants).toHaveLength(1);
    expect(state.tenants[0].slug).toBe("alpha");
    expect(state.tenants[0].displayName).toBe("Alpha Academy");
    expect(state.tenants[0].lastFingerprintB64).toBeNull();
    expect(state.tenants[0].lastVerifiedAt).toBeNull();
  });

  it("refuses duplicate slugs with a typed error", async () => {
    await addTenant("alpha", "Alpha Academy");
    await expect(addTenant("alpha", "Alpha Two")).rejects.toThrow(
      /already known/
    );
  });

  it("activeSlug defaults to the first-added tenant", async () => {
    const next = await addTenant("alpha", "Alpha");
    expect(next.activeSlug).toBe("alpha");
  });

  it("subsequent adds preserve existing activeSlug", async () => {
    await addTenant("alpha", "Alpha");
    const next = await addTenant("beta", "Beta");
    expect(next.activeSlug).toBe("alpha");
    expect(next.tenants.map((t) => t.slug)).toEqual(["alpha", "beta"]);
  });
});

describe("tenant_switcher setActiveTenant", () => {
  it("updates state when slug is known", async () => {
    await addTenant("alpha", "Alpha");
    await addTenant("beta", "Beta");
    const next = await setActiveTenant("beta");
    expect(next.activeSlug).toBe("beta");
  });

  it("is a no-op (and does NOT corrupt) when slug is unknown", async () => {
    await addTenant("alpha", "Alpha");
    const before = await getKnownTenants();
    const after = await setActiveTenant("nonexistent-slug");
    expect(after.activeSlug).toBe(before.activeSlug);
    expect(after.tenants).toEqual(before.tenants);
  });
});

describe("tenant_switcher removeTenant", () => {
  it("removing the active tenant resets activeSlug to the next row", async () => {
    await addTenant("alpha", "Alpha");
    await addTenant("beta", "Beta");
    const next = await removeTenant("alpha");
    expect(next.tenants).toHaveLength(1);
    expect(next.tenants[0].slug).toBe("beta");
    expect(next.activeSlug).toBe("beta");
  });

  it("removing the last tenant resets activeSlug to null", async () => {
    await addTenant("alpha", "Alpha");
    const next = await removeTenant("alpha");
    expect(next.tenants).toHaveLength(0);
    expect(next.activeSlug).toBeNull();
  });
});

describe("formatFingerprintForDisplay", () => {
  it("groups hex bytes in 4-char blocks separated by spaces", async () => {
    // 4 bytes 0xa1 0xb2 0xc3 0xd4 → "a1b2c3d4" → "a1b2 c3d4"
    const bytes = Uint8Array.from([0xa1, 0xb2, 0xc3, 0xd4]);
    const b64 = btoa(String.fromCharCode(...bytes));
    expect(formatFingerprintForDisplay(b64)).toBe("a1b2 c3d4");
  });

  it("returns empty string for empty input and falls back on invalid b64", () => {
    expect(formatFingerprintForDisplay("")).toBe("");
    // Force the failure path: shadow globalThis.atob with a thrower.
    const orig = (globalThis as unknown as { atob: (s: string) => string })
      .atob;
    (globalThis as unknown as { atob: (s: string) => string }).atob = () => {
      throw new Error("not b64");
    };
    try {
      expect(formatFingerprintForDisplay("###not-b64###")).toBe(
        "###not-b64###"
      );
    } finally {
      (globalThis as unknown as { atob: (s: string) => string }).atob = orig;
    }
  });
});

describe("fetchAndRecordPubkey", () => {
  it("calls fetch with ?tenant=<slug> and records the fingerprint", async () => {
    await addTenant("alpha", "Alpha");
    const seenUrls: string[] = [];
    const fakeFetch = vi.fn(async (url: string) => {
      seenUrls.push(url);
      return {
        ok: true,
        status: 200,
        json: async () => ({
          ok: true,
          tenant_slug: "alpha",
          public_key_b64: "PUBKEY_AAAA",
          key_version: "v1",
          fingerprint_b64: "FINGERPRINT_AAAA",
          encryption_scheme: "libsodium-secretbox-x25519-sealed",
        }),
      };
    });

    const body = await fetchAndRecordPubkey(
      "https://example.test",
      "alpha",
      fakeFetch
    );
    expect(body.fingerprint_b64).toBe("FINGERPRINT_AAAA");
    expect(seenUrls).toHaveLength(1);
    expect(seenUrls[0]).toContain("/companion/server-pubkey/?tenant=alpha");

    const after = await getKnownTenants();
    expect(after.tenants[0].lastFingerprintB64).toBe("FINGERPRINT_AAAA");
  });

  it("throws on non-OK HTTP and does NOT record a fingerprint", async () => {
    await addTenant("alpha", "Alpha");
    const fakeFetch = vi.fn(async () => ({
      ok: false,
      status: 404,
      json: async () => ({ ok: false, code: "tenant_not_found" }),
    }));
    await expect(
      fetchAndRecordPubkey("https://example.test", "alpha", fakeFetch)
    ).rejects.toThrow(/HTTP 404/);
    const after = await getKnownTenants();
    expect(after.tenants[0].lastFingerprintB64).toBeNull();
  });
});

describe("tenant_switcher edge cases", () => {
  it("getKnownTenants on virgin storage returns the empty state", async () => {
    const state = await getKnownTenants();
    expect(state).toEqual({ tenants: [], activeSlug: null });
    expect(EMPTY_STATE.tenants).toHaveLength(0);
    expect(EMPTY_STATE.activeSlug).toBeNull();
  });

  it("markVerified stamps lastVerifiedAt on the named tenant only", async () => {
    await addTenant("alpha", "Alpha");
    await addTenant("beta", "Beta");
    const stamp = "2026-05-19T18:30:00.000Z";
    const next = await markVerified("alpha", stamp);
    const alpha = next.tenants.find((t) => t.slug === "alpha");
    const beta = next.tenants.find((t) => t.slug === "beta");
    expect(alpha?.lastVerifiedAt).toBe(stamp);
    expect(beta?.lastVerifiedAt).toBeNull();
  });

  it("recordFingerprint is independent of markVerified", async () => {
    await addTenant("alpha", "Alpha");
    await recordFingerprint("alpha", "FPFPFP");
    const state = await getKnownTenants();
    expect(state.tenants[0].lastFingerprintB64).toBe("FPFPFP");
    expect(state.tenants[0].lastVerifiedAt).toBeNull();
  });

  it("addTenant rejects empty slug", async () => {
    await expect(addTenant("", "Whatever")).rejects.toThrow(
      /non-empty string/
    );
    await expect(addTenant("   ", "Whatever")).rejects.toThrow(
      /non-empty string/
    );
  });
});
