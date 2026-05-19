/**
 * HMAC-SHA256 webhook signature verifier.
 *
 * Dual-runtime: detects WebCrypto (`globalThis.crypto.subtle`) first
 * for browsers + Node 19+ + Edge runtimes; falls back to `node:crypto`
 * when running on older Node releases. Zero runtime dependencies.
 *
 * Header contract (set by the RunMyCampus platform on outbound deliveries):
 *
 *   X-RunMyCampus-Signature  →  sha256=<lowercase-hex-digest>
 *   X-RunMyCampus-Timestamp  →  Unix seconds (integer string)
 *   X-RunMyCampus-Event      →  Dotted event class (e.g. "migration.bundle.completed")
 *   X-RunMyCampus-Version    →  Signature format version ("v1" today)
 *
 * SECURITY: Constant-time compare is non-negotiable. In Node we use
 * `crypto.timingSafeEqual`; in the browser we use a manual XOR fold
 * over both encoded strings (WebCrypto exposes no string-input
 * `timingSafeEqual`). DO NOT replace either with `==` / `===`.
 */

import { BadSignatureError, ClockSkewError, MissingHeaderError, UnsupportedAlgorithmError, VerificationError } from "./errors";

/** Public header names the platform writes; do not hard-code in caller code. */
export const SIGNATURE_HEADER = "X-RunMyCampus-Signature";
export const TIMESTAMP_HEADER = "X-RunMyCampus-Timestamp";
export const EVENT_HEADER = "X-RunMyCampus-Event";
export const VERSION_HEADER = "X-RunMyCampus-Version";

/**
 * v3.37.0 — legacy header aliases for the 2026-05-19 → 2026-08-18
 * dual-emit migration window. Receivers built against the original
 * `X-Migration-Cloud-*` family stay supported until they migrate, via
 * `verify(..., { acceptLegacy: true })`. Default is `true` until 2026-08-18.
 */
export const LEGACY_SIGNATURE_HEADER = "X-Migration-Cloud-Signature";
export const LEGACY_TIMESTAMP_HEADER = "X-Migration-Cloud-Timestamp";
export const LEGACY_EVENT_HEADER = "X-Migration-Cloud-Event";
export const LEGACY_VERSION_HEADER = "X-Migration-Cloud-Version";

/** Signature prefix that identifies the digest algorithm. */
export const SUPPORTED_PREFIX = "sha256=";

/** Default clock-skew tolerance — matches Stripe / GitHub / Twilio. */
export const DEFAULT_TOLERANCE_SECONDS = 300;

export type BytesLike = string | Uint8Array | ArrayBuffer | ArrayBufferView;

/** Coerce a JS value into a Uint8Array. */
function _toUint8(value: BytesLike | null | undefined): Uint8Array {
  if (value === null || value === undefined) {
    return new Uint8Array(0);
  }
  if (value instanceof Uint8Array) {
    return value;
  }
  if (value instanceof ArrayBuffer) {
    return new Uint8Array(value);
  }
  if (ArrayBuffer.isView(value)) {
    return new Uint8Array(
      (value as ArrayBufferView).buffer,
      (value as ArrayBufferView).byteOffset,
      (value as ArrayBufferView).byteLength,
    );
  }
  if (typeof value === "string") {
    return new TextEncoder().encode(value);
  }
  throw new TypeError("verifier: unsupported body / secret value type");
}

interface SubtleLike {
  importKey(
    format: "raw",
    keyData: BufferSource,
    algorithm: { name: "HMAC"; hash: "SHA-256" },
    extractable: false,
    keyUsages: ["sign"],
  ): Promise<CryptoKey>;
  sign(
    algorithm: "HMAC",
    key: CryptoKey,
    data: BufferSource,
  ): Promise<ArrayBuffer>;
}

function _getSubtle(): SubtleLike | null {
  const g: any = globalThis as any;
  if (g && g.crypto && g.crypto.subtle) return g.crypto.subtle as SubtleLike;
  return null;
}

interface NodeCryptoLike {
  createHmac(alg: string, key: Uint8Array | string): { update(d: Uint8Array): any; digest(enc: "hex"): string };
  timingSafeEqual(a: Uint8Array, b: Uint8Array): boolean;
  webcrypto?: { subtle: SubtleLike };
}

function _getNodeCrypto(): NodeCryptoLike | null {
  // Avoid a literal `require("crypto")` call so bundlers targeting the
  // browser can tree-shake this out. We instead probe `globalThis`'s
  // `process` to ensure we're in Node, then dynamic-`require`.
  const g: any = globalThis as any;
  if (
    typeof g.process === "undefined" ||
    !g.process ||
    !g.process.versions ||
    !g.process.versions.node
  ) {
    return null;
  }
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  try {
    // `eval` keeps tools like esbuild from statically resolving this in
    // browser builds — runtime-only.
    // eslint-disable-next-line no-eval
    const req = (0, eval)("require");
    return req("crypto") as NodeCryptoLike;
  } catch {
    return null;
  }
}

/** Compute the HMAC-SHA256 of `body` under `secret` and return hex (lowercase). */
async function _hmacSha256Hex(
  bodyBytes: Uint8Array,
  secretBytes: Uint8Array,
): Promise<string> {
  const subtle = _getSubtle();
  if (subtle) {
    // Cast through `unknown` — TS 5.7+ tightened DOM `BufferSource` to
    // require ArrayBuffer (not ArrayBufferLike, which could be
    // SharedArrayBuffer). At runtime Uint8Array IS a BufferSource.
    const key = await subtle.importKey(
      "raw",
      secretBytes as unknown as ArrayBuffer,
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"],
    );
    const sigBuf = await subtle.sign("HMAC", key, bodyBytes as unknown as ArrayBuffer);
    return _bytesToHex(new Uint8Array(sigBuf));
  }
  // Node-only fallback (Node 16–18 without webcrypto-as-global).
  const node = _getNodeCrypto();
  if (node && node.createHmac) {
    const mac = node.createHmac("sha256", secretBytes);
    mac.update(bodyBytes);
    return mac.digest("hex");
  }
  throw new VerificationError(
    "verifier: no HMAC-SHA256 crypto backend available in this runtime",
  );
}

function _bytesToHex(bytes: Uint8Array): string {
  let hex = "";
  for (let i = 0; i < bytes.length; i++) {
    const b = bytes[i].toString(16);
    hex += b.length === 1 ? "0" + b : b;
  }
  return hex;
}

/**
 * Constant-time string equality over ASCII strings (the signature
 * header form). Always touches the full length regardless of mismatch
 * position.
 *
 * Note: length mismatch IS leaked (same posture as Python
 * `hmac.compare_digest` and Node `crypto.timingSafeEqual`).
 */
function _constantTimeEqual(a: string, b: string): boolean {
  // Prefer Node's `timingSafeEqual` when available — it's hardened in C++.
  const node = _getNodeCrypto();
  if (node && node.timingSafeEqual) {
    const aB = new TextEncoder().encode(a);
    const bB = new TextEncoder().encode(b);
    if (aB.length !== bB.length) return false;
    try {
      return node.timingSafeEqual(aB, bB);
    } catch {
      // fall through to manual fold
    }
  }
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) {
    diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return diff === 0;
}

/** Normalize a header value to string (or null when absent / unparseable). */
function _coerceHeader(value: string | Uint8Array | string[] | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value.trim();
  if (value instanceof Uint8Array) {
    try {
      return new TextDecoder("utf-8", { fatal: true }).decode(value).trim();
    } catch {
      return null;
    }
  }
  if (Array.isArray(value) && value.length > 0) {
    return _coerceHeader(value[0]);
  }
  return null;
}

/**
 * Return `sha256=<hex>` for the given raw body + secret.
 * Useful for unit tests and replay tooling. Do NOT use the output
 * to compare against a header with `===`; use `verifySignature` so
 * the compare runs in constant time.
 */
export async function computeSignature(
  body: BytesLike,
  secret: BytesLike,
): Promise<string> {
  const bodyBytes = _toUint8(body);
  const secretBytes = _toUint8(secret);
  const hex = await _hmacSha256Hex(bodyBytes, secretBytes);
  return SUPPORTED_PREFIX + hex;
}

export interface VerifyOptions {
  /** Value of the `X-RunMyCampus-Timestamp` header (string seconds). */
  timestampHeader?: string | Uint8Array | string[] | null;
  /** Max accepted clock skew (seconds). Default 300. */
  toleranceSeconds?: number;
  /** Override for the current unix-time (seconds, float). Useful in tests. */
  now?: number;
}

/**
 * Throw on any failure; resolve to `undefined` on success.
 *
 * Use this when you want to log WHY verification failed (without
 * leaking secret material). All thrown errors derive from
 * {@link VerificationError}.
 */
export async function verifySignatureStrict(
  body: BytesLike,
  signatureHeader: string | Uint8Array | string[] | null | undefined,
  secret: BytesLike,
  opts: VerifyOptions = {},
): Promise<void> {
  const headerStr = _coerceHeader(signatureHeader as any);
  if (!headerStr) {
    throw new MissingHeaderError(
      `webhook verifier: missing or empty ${SIGNATURE_HEADER} header`,
    );
  }
  if (!headerStr.startsWith(SUPPORTED_PREFIX)) {
    throw new UnsupportedAlgorithmError(
      "webhook verifier: signature algorithm not supported by this SDK " +
        "version (only 'sha256=' accepted); upgrade the verifier package.",
    );
  }
  const expected = await computeSignature(body, secret);
  if (!_constantTimeEqual(expected, headerStr)) {
    throw new BadSignatureError(
      "webhook verifier: signature did not match HMAC of the body under " +
        "the given secret (body tampered, wrong secret, or body bytes " +
        "are not the canonical bytes the platform signed)",
    );
  }

  // Clock-skew check is opt-in: enforced only when the timestamp header
  // is provided by the caller.
  if (opts.timestampHeader === undefined || opts.timestampHeader === null) {
    return;
  }
  const tsStr = _coerceHeader(opts.timestampHeader);
  if (!tsStr) {
    throw new MissingHeaderError(
      `webhook verifier: ${TIMESTAMP_HEADER} present but empty`,
    );
  }
  const signedAt = Number(tsStr);
  if (!Number.isFinite(signedAt)) {
    throw new MissingHeaderError(
      `webhook verifier: ${TIMESTAMP_HEADER} is not a numeric unix-seconds value`,
    );
  }
  const tolerance = Number(opts.toleranceSeconds ?? DEFAULT_TOLERANCE_SECONDS);
  const now = Number(opts.now ?? Date.now() / 1000);
  const skew = Math.abs(now - signedAt);
  if (skew > tolerance) {
    throw new ClockSkewError(
      `webhook verifier: signed timestamp is outside the ${tolerance}-second tolerance window`,
      skew,
    );
  }
}

/**
 * Boolean lenient verifier — resolves to `true` iff every check
 * passes; `false` on ANY failure (no exceptions surfaced).
 *
 * Use this in fail-closed middleware that doesn't need to dispatch
 * on the failure mode.
 *
 * @deprecated since 1.0.0-rc.1 — use {@link verify} instead, which
 *   accepts the full header map and transparently falls back across
 *   the canonical / legacy header families, returning a
 *   {@link VerifyResult} with non-sensitive diagnostics.
 *   `verifySignature` continues to work but will be removed in 2.0.
 *   See `MIGRATION_TO_1_0.md`.
 */
export async function verifySignature(
  body: BytesLike,
  signatureHeader: string | Uint8Array | string[] | null | undefined,
  secret: BytesLike,
  opts: VerifyOptions = {},
): Promise<boolean> {
  try {
    await verifySignatureStrict(body, signatureHeader, secret, opts);
    return true;
  } catch (err) {
    if (err instanceof VerificationError) return false;
    // Re-throw unexpected errors (e.g. WebCrypto/Node-crypto unavailable).
    // Customer middleware should treat those as a 500, not a 401.
    throw err;
  }
}

// ─── v3.37.0 dual-header-family `verify` API ─────────────────────────────

/**
 * Result of {@link verify} — boolean `valid` plus non-sensitive
 * diagnostics. NEVER contains secret/signature bytes.
 */
export interface VerifyResult {
  valid: boolean;
  /**
   * True iff the signature came from the legacy
   * `X-Migration-Cloud-Signature` header rather than the canonical
   * `X-RunMyCampus-Signature`. Subscribers should warn-log when this
   * flips true so they know to migrate before the dual-emit window
   * closes on 2026-08-18.
   */
  usedLegacyHeaderFamily: boolean;
  /** Header NAME the verifier consumed. Empty when both were absent. */
  signatureHeaderName: string;
  /**
   * Empty when `valid` is true; a short non-sensitive category otherwise:
   * `"missing-header" | "unsupported-algorithm" | "bad-signature" |
   * "clock-skew" | "legacy-rejected"`.
   */
  reason: string;
}

export type HeaderValue = string | Uint8Array | string[] | null | undefined;

export interface HeaderMap {
  get?(name: string): HeaderValue;
  [key: string]: any;
}

export interface VerifyApiOptions {
  /**
   * Accept the legacy `X-Migration-Cloud-*` header family as a fallback
   * when the new family is absent. Default `true` for the 2026-05-19 →
   * 2026-08-18 migration window. Flip to `false` after the cutover.
   */
  acceptLegacy?: boolean;
  /** Max accepted clock skew (seconds). Default 300. */
  toleranceSeconds?: number;
  /** Override for the current unix-time (seconds, float). Useful in tests. */
  now?: number;
}

/**
 * Case-insensitive header lookup. Accepts both Headers-like (with `get`)
 * and plain-object headers. Returns the first matching value or null.
 */
function _getHeader(headers: HeaderMap, name: string): HeaderValue {
  if (!headers) return null;
  // Headers-like object (`fetch` Response.headers, Express req.headers
  // with a custom Headers wrapper, etc.). The Headers `get` is itself
  // case-insensitive, so any case variant works.
  if (typeof headers.get === "function") {
    const v = headers.get(name);
    if (v !== null && v !== undefined) return v as HeaderValue;
    return null;
  }
  // Plain object — Node usually normalizes to lowercase, but HTTP header
  // names are case-insensitive and some callers pass mixed-case maps.
  const candidates = [name, name.toLowerCase(), name.toUpperCase()];
  for (const cand of candidates) {
    const v = (headers as Record<string, HeaderValue>)[cand];
    if (v !== null && v !== undefined) return v;
  }
  const target = name.toLowerCase();
  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() !== target) continue;
    const v = (headers as Record<string, HeaderValue>)[key];
    if (v !== null && v !== undefined) return v;
  }
  return null;
}

/**
 * v3.37.0 — verify a delivery from EITHER header family.
 *
 * Preference order: the canonical `X-RunMyCampus-Signature` is consulted
 * first; the legacy `X-Migration-Cloud-Signature` is the fallback IFF
 * `acceptLegacy=true` (the default during the 2026-05-19 → 2026-08-18
 * dual-emit window). After 2026-08-18 callers should flip
 * `acceptLegacy=false` to fail-closed on legacy-only deliveries.
 *
 * Returned {@link VerifyResult} carries `usedLegacyHeaderFamily` so
 * subscriber middleware can warn-log without changing fail-closed
 * posture.
 *
 * Constant-time compare is inherited from {@link verifySignatureStrict}
 * (Node `timingSafeEqual` when available, manual XOR fold otherwise).
 */
export async function verify(
  headers: HeaderMap,
  body: BytesLike,
  secret: BytesLike,
  opts: VerifyApiOptions = {},
): Promise<VerifyResult> {
  const acceptLegacy = opts.acceptLegacy !== false; // default true
  const newSig = _getHeader(headers, SIGNATURE_HEADER);
  const legacySig = _getHeader(headers, LEGACY_SIGNATURE_HEADER);
  const newTs = _getHeader(headers, TIMESTAMP_HEADER);
  const legacyTs = _getHeader(headers, LEGACY_TIMESTAMP_HEADER);

  let signatureValue: HeaderValue;
  let timestampValue: HeaderValue;
  let headerName: string;
  let usedLegacy = false;

  if (newSig !== null && newSig !== undefined && _coerceHeader(newSig)) {
    signatureValue = newSig;
    timestampValue = newTs;
    headerName = SIGNATURE_HEADER;
  } else if (legacySig !== null && legacySig !== undefined && _coerceHeader(legacySig)) {
    if (!acceptLegacy) {
      return {
        valid: false,
        usedLegacyHeaderFamily: true,
        signatureHeaderName: LEGACY_SIGNATURE_HEADER,
        reason: "legacy-rejected",
      };
    }
    signatureValue = legacySig;
    timestampValue = legacyTs;
    headerName = LEGACY_SIGNATURE_HEADER;
    usedLegacy = true;
  } else {
    return {
      valid: false,
      usedLegacyHeaderFamily: false,
      signatureHeaderName: "",
      reason: "missing-header",
    };
  }

  const strictOpts: VerifyOptions = {
    timestampHeader: timestampValue,
    toleranceSeconds: opts.toleranceSeconds,
    now: opts.now,
  };
  try {
    await verifySignatureStrict(body, signatureValue, secret, strictOpts);
    return {
      valid: true,
      usedLegacyHeaderFamily: usedLegacy,
      signatureHeaderName: headerName,
      reason: "",
    };
  } catch (err) {
    let reason = "bad-signature";
    if (err instanceof MissingHeaderError) reason = "missing-header";
    else if (err instanceof UnsupportedAlgorithmError) reason = "unsupported-algorithm";
    else if (err instanceof ClockSkewError) reason = "clock-skew";
    else if (err instanceof BadSignatureError) reason = "bad-signature";
    else if (!(err instanceof VerificationError)) throw err;
    return {
      valid: false,
      usedLegacyHeaderFamily: usedLegacy,
      signatureHeaderName: headerName,
      reason,
    };
  }
}
