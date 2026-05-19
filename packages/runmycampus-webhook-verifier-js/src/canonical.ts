/**
 * Canonical JSON serializer used for webhook signing.
 *
 * Byte-for-byte twin of the Python implementation at
 * ../../runmycampus-webhook-verifier-py/src/runmycampus_webhook_verifier/_canonical.py.
 * Parity is verified in CI against the shared fixture file at
 * test/fixtures/canonical-cases.json (both packages read it).
 *
 * Rules:
 *   - Object keys sorted lexicographically (UTF-16 code-unit order,
 *     matching Python `sorted(str)` and JS `[].sort()`).
 *   - No whitespace between tokens.
 *   - UTF-8 output bytes; non-ASCII emitted literally (matches
 *     `JSON.stringify` default which does NOT escape U+0080+).
 *   - `NaN` / `Infinity` / `-Infinity` are NOT representable — we
 *     refuse to emit them (throws `CanonicalJSONError`).
 *   - Floats emitted via JS's default `toString()` round-trip
 *     (mirrors Python repr() on the wire for representable ints &
 *     simple decimals; avoid floats in signed payloads if you can).
 */

/** Raised when an input cannot be canonically serialized. */
export class CanonicalJSONError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "CanonicalJSONError";
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

function isPlainObject(v: unknown): v is Record<string, unknown> {
  if (v === null || typeof v !== "object") return false;
  // Reject Date / Map / Set / typed arrays / etc. — they don't have a
  // canonical JSON form and the Python twin would reject them too.
  const proto = Object.getPrototypeOf(v);
  return proto === Object.prototype || proto === null;
}

/**
 * Serialize a single value to its canonical string form.
 * Recursive — sorts dict keys, no whitespace between tokens.
 */
function _encode(value: unknown): string {
  if (value === null) return "null";
  if (value === true) return "true";
  if (value === false) return "false";

  if (typeof value === "number") {
    if (!Number.isFinite(value)) {
      throw new CanonicalJSONError(
        "canonical JSON: NaN / Infinity / -Infinity are not representable; " +
          "coerce to null / string upstream.",
      );
    }
    // Integers serialize identically across runtimes. Floats are
    // emitted via JS toString which is JSON-compatible.
    return JSON.stringify(value);
  }

  if (typeof value === "string") {
    // JSON.stringify of a string handles control-char escaping AND
    // wraps in quotes. `ensure_ascii=False` parity: we want the SAME
    // output Python emits with non-ASCII characters left literal —
    // which IS exactly what JSON.stringify does by default in JS.
    return JSON.stringify(value);
  }

  if (Array.isArray(value)) {
    const parts: string[] = [];
    for (const item of value) {
      parts.push(_encode(item));
    }
    return "[" + parts.join(",") + "]";
  }

  if (isPlainObject(value)) {
    const keys = Object.keys(value).sort();
    const parts: string[] = [];
    for (const k of keys) {
      // Skip `undefined` values (mirrors JSON.stringify behavior +
      // matches Python where you can't have an undefined dict value
      // — best to require callers strip these upstream, but be
      // tolerant here).
      const v = (value as Record<string, unknown>)[k];
      if (v === undefined) continue;
      parts.push(JSON.stringify(k) + ":" + _encode(v));
    }
    return "{" + parts.join(",") + "}";
  }

  if (typeof value === "undefined") {
    throw new CanonicalJSONError(
      "canonical JSON: top-level undefined is not representable; coerce to null upstream.",
    );
  }

  throw new CanonicalJSONError(
    `canonical JSON: type ${typeof value} is not JSON-serializable; coerce upstream.`,
  );
}

/** Return canonical UTF-8 bytes for `value`. */
export function canonicalize(value: unknown): Uint8Array {
  const text = _encode(value);
  // TextEncoder is universally available in Node 16+, all evergreen
  // browsers, and Edge runtimes. Zero-dependency.
  return new TextEncoder().encode(text);
}

/** Return canonical string form (for fixture-comparison and debugging). */
export function canonicalizeToString(value: unknown): string {
  return _encode(value);
}

/** Convenience: `sha256(canonicalize(value))` as lowercase hex.
 *  Caller-provided helper (no built-in hex helper in WebCrypto).
 */
export async function canonicalSha256Hex(value: unknown): Promise<string> {
  const bytes = canonicalize(value);
  const subtle = _getSubtle();
  if (!subtle) {
    throw new Error(
      "canonicalSha256Hex: no WebCrypto subtle available in this runtime",
    );
  }
  // Cast through `BufferSource` — Uint8Array<ArrayBufferLike> is functionally
  // a BufferSource at runtime; TS 5.7+ tightened the DOM lib types to refuse
  // the implicit conversion when the backing buffer could be SharedArrayBuffer.
  const digest = await subtle.digest("SHA-256", bytes as unknown as ArrayBuffer);
  return _bytesToHex(new Uint8Array(digest));
}

function _getSubtle(): SubtleCrypto | null {
  // Browser / Node 19+ / Edge: globalThis.crypto.subtle
  // Node 16–18: require("crypto").webcrypto.subtle (we don't `require`
  // here because we want this module to be ESM-clean; the verifier
  // module handles the Node path).
  const g: any = globalThis as any;
  if (g && g.crypto && g.crypto.subtle) return g.crypto.subtle;
  return null;
}

function _bytesToHex(bytes: Uint8Array): string {
  let hex = "";
  for (let i = 0; i < bytes.length; i++) {
    const b = bytes[i].toString(16);
    hex += b.length === 1 ? "0" + b : b;
  }
  return hex;
}
