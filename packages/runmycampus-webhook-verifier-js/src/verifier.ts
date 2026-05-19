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
