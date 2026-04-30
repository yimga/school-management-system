/**
 * Minimal RunMyCampus JavaScript SDK (fetch-based).
 * Matches Python webhook signing: HMAC-SHA256 hex with prefix "sha256=".
 */

import crypto from "node:crypto";

export function signPayload(secret, bodyUtf8) {
  const h = crypto.createHmac("sha256", secret || "");
  h.update(bodyUtf8);
  return `sha256=${h.digest("hex")}`;
}

export function verifyWebhookSignature(secret, bodyUtf8, headerValue) {
  if (!headerValue || bodyUtf8 == null) return false;
  const expected = signPayload(secret, bodyUtf8);
  const a = Buffer.from(expected);
  const b = Buffer.from(String(headerValue).trim());
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

export class RunMyCampusClient {
  /**
   * @param {string} baseUrl e.g. https://school.runmycampus.com
   */
  constructor(baseUrl) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.headers = { Accept: "application/json" };
  }

  setBearerToken(token) {
    this.headers = { ...this.headers, Authorization: `Bearer ${token}` };
  }

  async requestWithRetries(path, options = {}, maxAttempts = 4) {
    const delays = [250, 1000, 3000];
    let lastErr;
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        const url = path.startsWith("/")
          ? `${this.baseUrl}${path}`
          : `${this.baseUrl}/${path}`;
        const merged = {
          ...options,
          headers: { ...this.headers, ...(options.headers || {}) },
        };
        const res = await fetch(url, merged);
        if (res.status === 429 || res.status >= 500) {
          if (attempt < maxAttempts - 1) {
            await new Promise((r) =>
              setTimeout(r, delays[Math.min(attempt, delays.length - 1)])
            );
            continue;
          }
        }
        return res;
      } catch (e) {
        lastErr = e;
        if (attempt < maxAttempts - 1) {
          await new Promise((r) =>
            setTimeout(r, delays[Math.min(attempt, delays.length - 1)])
          );
          continue;
        }
        throw e;
      }
    }
    throw lastErr || new Error("request failed");
  }
}
