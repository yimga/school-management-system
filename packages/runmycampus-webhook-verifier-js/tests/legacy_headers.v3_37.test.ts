/**
 * v3.37.0 — packaged JS SDK `verify(headers, body, secret, { acceptLegacy })`
 * tests. Parity with the Python SDK's ``test_legacy_headers_v3_37.py``:
 *
 *   1. New header family verifies; `usedLegacyHeaderFamily` is `false`.
 *   2. Legacy header family verifies when `acceptLegacy=true` (default).
 *   3. Legacy family rejected when `acceptLegacy=false`; non-sensitive
 *      `reason: "legacy-rejected"`.
 *   4. Mixed headers (both families present) prefer the NEW family.
 *
 * All comparisons in the SDK use `crypto.timingSafeEqual` (Node) or
 * a manual XOR fold (browser). The tests themselves drive the public
 * API and never reach into SDK internals.
 */

import { describe, expect, it } from "vitest";
import { createHmac } from "node:crypto";
import {
  canonicalize,
  LEGACY_SIGNATURE_HEADER,
  LEGACY_TIMESTAMP_HEADER,
  SIGNATURE_HEADER,
  TIMESTAMP_HEADER,
  verify,
} from "../src/index";
import type { VerifyResult } from "../src/index";

const SECRET = "whsec_test_v3_37_NEVER_USE_IN_PRODUCTION";
const PAYLOAD = {
  event: "migration.bundle.completed",
  delivery_id: "d_v3_37_xyz",
  tenant_id: 7,
};

function sign(body: Uint8Array, secret: string = SECRET): string {
  const mac = createHmac("sha256", secret);
  mac.update(body);
  return "sha256=" + mac.digest("hex");
}

describe("v3.37 dual header-family verify()", () => {
  // 1) New family verifies; usedLegacyHeaderFamily is false.
  it("new header family verifies and flags legacy false", async () => {
    const body = canonicalize(PAYLOAD);
    const signature = sign(body);
    const headers = { [SIGNATURE_HEADER]: signature };
    const result: VerifyResult = await verify(headers, body, SECRET);
    expect(result.valid).toBe(true);
    expect(result.usedLegacyHeaderFamily).toBe(false);
    expect(result.signatureHeaderName).toBe(SIGNATURE_HEADER);
    expect(result.reason).toBe("");
  });

  // 2) Legacy family verifies when acceptLegacy=true (default).
  it("legacy family verifies when acceptLegacy=true (default)", async () => {
    const body = canonicalize(PAYLOAD);
    const signature = sign(body);
    const headers = { [LEGACY_SIGNATURE_HEADER]: signature };

    const result = await verify(headers, body, SECRET, { acceptLegacy: true });
    expect(result.valid).toBe(true);
    expect(result.usedLegacyHeaderFamily).toBe(true);
    expect(result.signatureHeaderName).toBe(LEGACY_SIGNATURE_HEADER);
    expect(result.reason).toBe("");

    const defaultResult = await verify(headers, body, SECRET);
    expect(defaultResult.valid).toBe(true);
    expect(defaultResult.usedLegacyHeaderFamily).toBe(true);
  });

  // 3) Legacy family rejected when acceptLegacy=false.
  it("legacy family rejected when acceptLegacy=false", async () => {
    const body = canonicalize(PAYLOAD);
    const signature = sign(body);
    const headers = { [LEGACY_SIGNATURE_HEADER]: signature };

    const result = await verify(headers, body, SECRET, { acceptLegacy: false });
    expect(result.valid).toBe(false);
    expect(result.usedLegacyHeaderFamily).toBe(true);
    expect(result.signatureHeaderName).toBe(LEGACY_SIGNATURE_HEADER);
    expect(result.reason).toBe("legacy-rejected");
    // Non-sensitive reason: secret + signature bytes must NEVER appear.
    expect(result.reason).not.toContain(SECRET);
    expect(result.reason).not.toContain(signature);
  });

  // 4) Mixed headers — new family preferred over legacy.
  it("mixed headers prefer the new family", async () => {
    const body = canonicalize(PAYLOAD);
    const goodSignature = sign(body);
    const bogusLegacy = "sha256=" + "0".repeat(64);
    const ts = "1715990400";
    const headers = {
      [SIGNATURE_HEADER]: goodSignature,
      [LEGACY_SIGNATURE_HEADER]: bogusLegacy,
      [TIMESTAMP_HEADER]: ts,
      [LEGACY_TIMESTAMP_HEADER]: ts,
    };
    // `now` pinned to the claimed timestamp so the clock-skew check has
    // nothing to complain about — this test is specifically asserting
    // header-family preference, not skew behavior.
    const result = await verify(headers, body, SECRET, {
      acceptLegacy: true,
      now: Number(ts),
    });
    expect(result.valid).toBe(true);
    expect(result.usedLegacyHeaderFamily).toBe(false);
    expect(result.signatureHeaderName).toBe(SIGNATURE_HEADER);
    expect(result.reason).toBe("");
  });

  it("plain-object header lookup is fully case-insensitive", async () => {
    const body = canonicalize(PAYLOAD);
    const signature = sign(body);
    const headers = { "x-RuNmYcAmPuS-sIgNaTuRe": signature };

    const result = await verify(headers, body, SECRET);

    expect(result.valid).toBe(true);
    expect(result.usedLegacyHeaderFamily).toBe(false);
    expect(result.signatureHeaderName).toBe(SIGNATURE_HEADER);
  });

  it("empty canonical signature falls back to legacy when accepted", async () => {
    const body = canonicalize(PAYLOAD);
    const signature = sign(body);
    const headers = {
      [SIGNATURE_HEADER]: "   ",
      [LEGACY_SIGNATURE_HEADER]: signature,
    };

    const result = await verify(headers, body, SECRET);

    expect(result.valid).toBe(true);
    expect(result.usedLegacyHeaderFamily).toBe(true);
    expect(result.signatureHeaderName).toBe(LEGACY_SIGNATURE_HEADER);
  });
});
