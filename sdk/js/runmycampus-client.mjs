/**
 * RunMyCampus HTTP client (ESM). Auth helpers, retries, EventSource subscription,
 * install deeplink helper, and webhook signature verification (HMAC-SHA256).
 * Node 18+ (global fetch) or bundlers that polyfill fetch.
 */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function shouldRetryStatus(status) {
  if (status == null) return true;
  return status === 429 || status >= 500;
}

/** WebCrypto / Node crypto compatible subtle digest for hex HMAC. */
async function hmacSha256Hex(secret, payload) {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(payload));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export class RunMyCampusClient {
  /**
   * @param {string} baseUrl - Tenant base, e.g. https://yourschool.example.com
   * @param {{ fetch?: typeof fetch, headers?: Record<string,string> }} [opts]
   */
  constructor(baseUrl, opts = {}) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this._fetch = opts.fetch ?? globalThis.fetch?.bind(globalThis);
    if (!this._fetch) {
      throw new Error("RunMyCampus JS SDK requires fetch (Node 18+ or polyfill)");
    }
    this._headers = new Headers(opts.headers || {});
    if (!this._headers.has("Accept")) {
      this._headers.set("Accept", "application/json");
    }
  }

  /** Persist bearer for session-style usage (integrators may wrap with token refresh). */
  setBearerToken(token) {
    this._headers.set("Authorization", `Bearer ${token}`);
  }

  /** Read Authorization bearer if present on internal headers. */
  getBearerToken() {
    const a = this._headers.get("Authorization") || "";
    return a.startsWith("Bearer ") ? a.slice(7).trim() : "";
  }

  _url(path) {
    return path.startsWith("/") ? `${this.baseUrl}${path}` : `${this.baseUrl}/${path}`;
  }

  async get(path, init = {}) {
    return this._fetch(this._url(path), { ...init, method: "GET", headers: this._mergeHeaders(init.headers) });
  }

  async post(path, init = {}) {
    return this._fetch(this._url(path), { ...init, method: "POST", headers: this._mergeHeaders(init.headers) });
  }

  _mergeHeaders(extra) {
    const h = new Headers(this._headers);
    if (extra && typeof Headers !== "undefined" && extra instanceof Headers) {
      extra.forEach((v, k) => h.set(k, v));
    } else if (extra && typeof extra === "object") {
      Object.entries(extra).forEach(([k, v]) => h.set(k, String(v)));
    }
    return h;
  }

  /**
   * GET with exponential backoff on 429 / 5xx (parity with Python client).
   */
  async requestWithRetries(method, path, init = {}, maxAttempts = 4, backoffSec = [0.25, 1, 3]) {
    let last;
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      last = await this._fetch(this._url(path), {
        ...init,
        method,
        headers: this._mergeHeaders(init.headers),
      });
      const sc = last.status;
      if (!shouldRetryStatus(sc) || attempt === maxAttempts - 1) {
        return last;
      }
      const delayMs = (backoffSec[Math.min(attempt, backoffSec.length - 1)] ?? 3) * 1000;
      await sleep(delayMs);
    }
    return last;
  }

  /**
   * GET /api/v1/platform/integration-context/ — requires same Authorization as other API calls.
   */
  async integrationContext() {
    return this.get("/api/v1/platform/integration-context/");
  }

  /**
   * Subscribe to Server-Sent Events (tenant events stream). Caller supplies full URL or path.
   * Returns native EventSource (browser) — Node callers should polyfill eventsource package.
   */
  subscribeEvents(pathOrUrl, options = {}) {
    const url = pathOrUrl.startsWith("http") ? pathOrUrl : this._url(pathOrUrl);
    const Es = globalThis.EventSource;
    if (!Es) {
      throw new Error("EventSource not available; use an EventSource polyfill in Node");
    }
    return new Es(url, options);
  }

  /**
   * Build tenant install / consent URL for guided onboarding (opens in browser).
   */
  installHelperUrl(marketplaceListingSlug, extraQuery = {}) {
    const u = new URL("/marketplace/", this.baseUrl);
    u.pathname = `/marketplace/${encodeURIComponent(marketplaceListingSlug)}/`;
    Object.entries(extraQuery).forEach(([k, v]) => u.searchParams.set(k, String(v)));
    return u.toString();
  }

  /**
   * Verify webhook raw body against X-Webhook-Signature (hex HMAC-SHA256). Timing-safe compare recommended by caller.
   */
  static async verifyWebhookSignature(rawBody, secret, signatureHex) {
    const expected = await hmacSha256Hex(secret, typeof rawBody === "string" ? rawBody : String(rawBody));
    return expected.toLowerCase() === String(signatureHex || "").toLowerCase();
  }
}

export default RunMyCampusClient;
