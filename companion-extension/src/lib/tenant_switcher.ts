/**
 * v3.37.0 — Multi-tenant switcher for the Companion popup.
 *
 * District-level operators frequently migrate 3-10 schools in parallel.
 * Without an explicit tenant switch they'd have to log in and out of
 * each subdomain in the popup, and the server-pubkey cache could carry
 * STALE keys keyed to whichever tenant happened to be active first.
 *
 * This module owns:
 *   * The list of "known tenants" the operator has added (slug +
 *     display name + last-seen fingerprint + last-verified timestamp).
 *   * The currently-active slug. Subsequent ``fetchServerPubkey`` calls
 *     pass this as ``?tenant=<slug>`` so the server returns the right
 *     keypair regardless of session cookie.
 *
 * Storage shape (chrome.storage.local key ``"tenant_switcher_v1"``):
 *
 *     {
 *       "tenants": [
 *         {
 *           "slug": "alpha-academy",
 *           "displayName": "Alpha Academy",
 *           "lastFingerprintB64": "Abc...",
 *           "lastVerifiedAt": "2026-05-19T18:30:00.000Z"
 *         }
 *       ],
 *       "activeSlug": "alpha-academy"
 *     }
 *
 * Defensive contracts:
 *   - Duplicate slugs are REFUSED with a typed Error (no silent merge).
 *   - Removing the active tenant resets ``activeSlug`` to the next
 *     remaining tenant (or ``null`` when the list goes empty).
 *   - All exported functions return Promises that resolve with the
 *     fresh post-mutation state so callers can avoid a second read.
 *   - No ``any`` types leak across the exported boundary.
 */

const STORAGE_KEY = "tenant_switcher_v1" as const;

export interface KnownTenant {
  slug: string;
  displayName: string;
  lastFingerprintB64: string | null;
  lastVerifiedAt: string | null;
}

export interface TenantSwitcherState {
  tenants: KnownTenant[];
  activeSlug: string | null;
}

/** Empty default returned when chrome.storage has nothing for us yet. */
export const EMPTY_STATE: TenantSwitcherState = Object.freeze({
  tenants: [],
  activeSlug: null,
}) as TenantSwitcherState;

/** ``chrome.storage.local`` typing shim. Tests inject a fake. */
export interface LocalStorageAreaLike {
  get(
    keys: string | string[] | Record<string, unknown>
  ): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
}

/** Resolve the active storage area. Tests override via setStorageBackend. */
let _storage: LocalStorageAreaLike | null = null;

export function setStorageBackend(backend: LocalStorageAreaLike | null): void {
  _storage = backend;
}

function getStorage(): LocalStorageAreaLike {
  if (_storage !== null) return _storage;
  // Best-effort wire to the real chrome.storage.local; if absent (e.g.
  // jsdom under vitest with no fake injected), surface a clear error.
  const g = globalThis as unknown as {
    chrome?: { storage?: { local?: LocalStorageAreaLike } };
  };
  const candidate = g.chrome?.storage?.local;
  if (candidate) return candidate;
  throw new Error(
    "tenant_switcher: no storage backend available (call setStorageBackend in tests)"
  );
}

/** Load + normalize the persisted state. Never throws on missing key. */
export async function getKnownTenants(): Promise<TenantSwitcherState> {
  const raw = await getStorage().get(STORAGE_KEY);
  const stored = raw[STORAGE_KEY];
  if (stored === undefined || stored === null) {
    return { tenants: [], activeSlug: null };
  }
  if (typeof stored !== "object") {
    return { tenants: [], activeSlug: null };
  }
  const s = stored as Partial<TenantSwitcherState>;
  const tenants: KnownTenant[] = Array.isArray(s.tenants)
    ? s.tenants
        .filter((t): t is KnownTenant => {
          return (
            !!t &&
            typeof t === "object" &&
            typeof (t as KnownTenant).slug === "string" &&
            typeof (t as KnownTenant).displayName === "string"
          );
        })
        .map((t) => ({
          slug: t.slug,
          displayName: t.displayName,
          lastFingerprintB64:
            typeof t.lastFingerprintB64 === "string"
              ? t.lastFingerprintB64
              : null,
          lastVerifiedAt:
            typeof t.lastVerifiedAt === "string" ? t.lastVerifiedAt : null,
        }))
    : [];
  const activeSlug =
    typeof s.activeSlug === "string" && tenants.some((t) => t.slug === s.activeSlug)
      ? s.activeSlug
      : tenants.length > 0
      ? tenants[0].slug
      : null;
  return { tenants, activeSlug };
}

async function _writeState(state: TenantSwitcherState): Promise<void> {
  await getStorage().set({ [STORAGE_KEY]: state });
}

/** Add a new tenant. Refuses duplicate slugs. */
export async function addTenant(
  slug: string,
  displayName: string
): Promise<TenantSwitcherState> {
  const cleanSlug = (slug || "").trim();
  const cleanName = (displayName || "").trim() || cleanSlug;
  if (!cleanSlug) {
    throw new Error("tenant_switcher: slug must be a non-empty string");
  }
  const state = await getKnownTenants();
  if (state.tenants.some((t) => t.slug === cleanSlug)) {
    throw new Error(`tenant_switcher: slug already known: ${cleanSlug}`);
  }
  const newTenant: KnownTenant = {
    slug: cleanSlug,
    displayName: cleanName,
    lastFingerprintB64: null,
    lastVerifiedAt: null,
  };
  const next: TenantSwitcherState = {
    tenants: [...state.tenants, newTenant],
    // First-add wins activeSlug; subsequent adds preserve the existing
    // selection so we don't surprise the operator mid-session.
    activeSlug: state.activeSlug ?? cleanSlug,
  };
  await _writeState(next);
  return next;
}

/** Set the active tenant. Unknown slug is a no-op (returns current state). */
export async function setActiveTenant(
  slug: string
): Promise<TenantSwitcherState> {
  const state = await getKnownTenants();
  if (!state.tenants.some((t) => t.slug === slug)) {
    // Defensive: refuse to corrupt activeSlug to an unknown value.
    return state;
  }
  const next: TenantSwitcherState = { ...state, activeSlug: slug };
  await _writeState(next);
  return next;
}

/** Remove a tenant. Resets activeSlug if it was the removed one. */
export async function removeTenant(
  slug: string
): Promise<TenantSwitcherState> {
  const state = await getKnownTenants();
  const tenants = state.tenants.filter((t) => t.slug !== slug);
  let activeSlug = state.activeSlug;
  if (state.activeSlug === slug) {
    activeSlug = tenants.length > 0 ? tenants[0].slug : null;
  }
  const next: TenantSwitcherState = { tenants, activeSlug };
  await _writeState(next);
  return next;
}

/** Record a freshly-fetched fingerprint for the named tenant. */
export async function recordFingerprint(
  slug: string,
  fingerprintB64: string
): Promise<TenantSwitcherState> {
  const state = await getKnownTenants();
  const tenants = state.tenants.map((t) =>
    t.slug === slug ? { ...t, lastFingerprintB64: fingerprintB64 } : t
  );
  const next: TenantSwitcherState = { ...state, tenants };
  await _writeState(next);
  return next;
}

/** Mark the active tenant's fingerprint as operator-verified (now). */
export async function markVerified(
  slug: string,
  whenIso?: string
): Promise<TenantSwitcherState> {
  const state = await getKnownTenants();
  const stamp = whenIso ?? new Date().toISOString();
  const tenants = state.tenants.map((t) =>
    t.slug === slug ? { ...t, lastVerifiedAt: stamp } : t
  );
  const next: TenantSwitcherState = { ...state, tenants };
  await _writeState(next);
  return next;
}

/**
 * Format a base64 fingerprint as 4-character-grouped hex for visual
 * side-by-side comparison against the Django admin's out-of-band copy.
 *
 * The server emits a base64-encoded SHA-256 prefix (16 bytes → 24 b64
 * chars w/ padding). We decode to bytes, hex-encode, then insert a
 * single space every 4 hex chars:
 *
 *     "a1b2c3d4e5f60718..." → "a1b2 c3d4 e5f6 0718 ..."
 *
 * Failsafe: if the input is not valid base64 the function returns the
 * input verbatim — the popup will then show the raw form and the
 * operator can still compare it character-for-character.
 */
export function formatFingerprintForDisplay(fingerprintB64: string): string {
  if (!fingerprintB64) return "";
  let hex: string;
  try {
    const bytes = _b64ToBytes(fingerprintB64);
    hex = Array.from(bytes)
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  } catch {
    return fingerprintB64;
  }
  const groups: string[] = [];
  for (let i = 0; i < hex.length; i += 4) {
    groups.push(hex.slice(i, i + 4));
  }
  return groups.join(" ");
}

function _b64ToBytes(b64: string): Uint8Array {
  // atob is available in browser + jsdom contexts; in Node-only test
  // contexts vitest's jsdom polyfills it.
  const a = (
    globalThis as unknown as { atob?: (s: string) => string }
  ).atob;
  if (typeof a !== "function") {
    throw new Error("atob unavailable");
  }
  const bin = a(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) {
    out[i] = bin.charCodeAt(i);
  }
  return out;
}

/**
 * Fetch the server pubkey for the active tenant (or a named one) and
 * record the returned fingerprint on the known-tenant row.
 *
 * The fetcher is parameterized so tests can inject a stub without
 * monkey-patching the global ``fetch``.
 */
export interface ServerPubkeyResponse {
  ok: boolean;
  tenant_slug?: string;
  public_key_b64: string;
  key_version: string;
  fingerprint_b64: string;
  encryption_scheme: string;
}

export type FetchLike = (
  url: string,
  init?: { method?: string; credentials?: string }
) => Promise<{
  ok: boolean;
  status: number;
  json: () => Promise<unknown>;
}>;

export async function fetchAndRecordPubkey(
  baseUrl: string,
  slug: string,
  fetchImpl: FetchLike
): Promise<ServerPubkeyResponse> {
  const cleanSlug = (slug || "").trim();
  if (!cleanSlug) {
    throw new Error("fetchAndRecordPubkey: slug required");
  }
  const url = `${baseUrl.replace(/\/+$/, "")}/companion/server-pubkey/?tenant=${encodeURIComponent(cleanSlug)}`;
  const resp = await fetchImpl(url, {
    method: "GET",
    credentials: "include",
  });
  if (!resp.ok) {
    throw new Error(
      `fetchAndRecordPubkey: HTTP ${resp.status} fetching pubkey for ${cleanSlug}`
    );
  }
  const body = (await resp.json()) as ServerPubkeyResponse;
  if (!body || typeof body !== "object" || !body.fingerprint_b64) {
    throw new Error("fetchAndRecordPubkey: malformed response");
  }
  await recordFingerprint(cleanSlug, body.fingerprint_b64);
  return body;
}
