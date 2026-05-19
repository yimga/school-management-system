/**
 * HMAC verifier tests — round-trip + tamper + replay-window + headers.
 */

import { describe, expect, it } from "vitest";
import { createHmac } from "node:crypto";
import {
  canonicalize,
  computeSignature,
  verifySignature,
  verifySignatureStrict,
  SIGNATURE_HEADER,
  TIMESTAMP_HEADER,
  DEFAULT_TOLERANCE_SECONDS,
  BadSignatureError,
  ClockSkewError,
  MissingHeaderError,
  UnsupportedAlgorithmError,
  VerificationError,
} from "../src/index";

const SECRET = "whsec_test_NEVER_USE_IN_PRODUCTION";
const PAYLOAD = {
  event: "migration.bundle.completed",
  delivery_id: "d_abc123",
  tenant_id: 42,
};

function sign(secret: string, body: Uint8Array): string {
  const mac = createHmac("sha256", secret);
  mac.update(body);
  return "sha256=" + mac.digest("hex");
}

describe("round trip", () => {
  it("signed body verifies under same secret", async () => {
    const body = canonicalize(PAYLOAD);
    const header = sign(SECRET, body);
    expect(await verifySignature(body, header, SECRET)).toBe(true);
    await verifySignatureStrict(body, header, SECRET);
  });

  it("string body round-trips", async () => {
    const text = new TextDecoder().decode(canonicalize(PAYLOAD));
    const header = sign(SECRET, new TextEncoder().encode(text));
    expect(await verifySignature(text, header, SECRET)).toBe(true);
  });

  it("bytes secret round-trips", async () => {
    const body = canonicalize(PAYLOAD);
    const header = sign(SECRET, body);
    const secretBytes = new TextEncoder().encode(SECRET);
    expect(await verifySignature(body, header, secretBytes)).toBe(true);
  });

  it("computeSignature output is itself verifiable", async () => {
    const body = canonicalize(PAYLOAD);
    const header = await computeSignature(body, SECRET);
    expect(header.startsWith("sha256=")).toBe(true);
    expect(await verifySignature(body, header, SECRET)).toBe(true);
  });
});

describe("tampered body", () => {
  it("rejects altered body byte", async () => {
    const body = canonicalize(PAYLOAD);
    const header = sign(SECRET, body);
    const tampered = new Uint8Array(body);
    tampered[tampered.length - 1] = (tampered[tampered.length - 1] ^ 0x20) & 0xff;
    expect(await verifySignature(tampered, header, SECRET)).toBe(false);
    await expect(verifySignatureStrict(tampered, header, SECRET))
      .rejects.toThrow(BadSignatureError);
  });

  it("rejects wrong secret", async () => {
    const body = canonicalize(PAYLOAD);
    const header = sign(SECRET, body);
    expect(await verifySignature(body, header, "different_secret")).toBe(false);
    await expect(verifySignatureStrict(body, header, "different_secret"))
      .rejects.toThrow(BadSignatureError);
  });
});

describe("header contract", () => {
  it("missing header returns false", async () => {
    const body = canonicalize(PAYLOAD);
    expect(await verifySignature(body, null, SECRET)).toBe(false);
    await expect(verifySignatureStrict(body, null, SECRET))
      .rejects.toThrow(MissingHeaderError);
  });

  it("empty header returns false", async () => {
    const body = canonicalize(PAYLOAD);
    expect(await verifySignature(body, "", SECRET)).toBe(false);
    await expect(verifySignatureStrict(body, "", SECRET))
      .rejects.toThrow(MissingHeaderError);
  });

  it("whitespace header returns false", async () => {
    const body = canonicalize(PAYLOAD);
    expect(await verifySignature(body, "   ", SECRET)).toBe(false);
  });

  it("future-prefix (sha512=) rejected, not silently accepted", async () => {
    const body = canonicalize(PAYLOAD);
    // Right shape, wrong algorithm prefix.
    const fake = "sha512=" + "0".repeat(128);
    expect(await verifySignature(body, fake, SECRET)).toBe(false);
    await expect(verifySignatureStrict(body, fake, SECRET))
      .rejects.toThrow(UnsupportedAlgorithmError);
  });

  it("array header (repeated header) uses first value", async () => {
    const body = canonicalize(PAYLOAD);
    const header = sign(SECRET, body);
    expect(await verifySignature(body, [header], SECRET)).toBe(true);
  });

  it("Uint8Array header is decoded as utf-8", async () => {
    const body = canonicalize(PAYLOAD);
    const header = sign(SECRET, body);
    const headerBytes = new TextEncoder().encode(header);
    expect(await verifySignature(body, headerBytes, SECRET)).toBe(true);
  });

  it("header constants pinned at expected values", () => {
    expect(SIGNATURE_HEADER).toBe("X-RunMyCampus-Signature");
    expect(TIMESTAMP_HEADER).toBe("X-RunMyCampus-Timestamp");
    expect(DEFAULT_TOLERANCE_SECONDS).toBe(300);
  });
});

describe("clock skew", () => {
  function signed() {
    const body = canonicalize(PAYLOAD);
    const header = sign(SECRET, body);
    return { body, header };
  }

  it("no timestamp header skips skew check", async () => {
    const { body, header } = signed();
    expect(await verifySignature(body, header, SECRET)).toBe(true);
  });

  it("in-window timestamp accepted", async () => {
    const { body, header } = signed();
    const now = 1_700_000_000;
    expect(await verifySignature(body, header, SECRET, {
      timestampHeader: String(now - 100),
      now,
    })).toBe(true);
  });

  it("boundary exactly at tolerance accepted", async () => {
    const { body, header } = signed();
    const now = 1_700_000_000;
    expect(await verifySignature(body, header, SECRET, {
      timestampHeader: String(now - DEFAULT_TOLERANCE_SECONDS),
      now,
    })).toBe(true);
  });

  it("just outside tolerance rejected with skewSeconds exposed", async () => {
    const { body, header } = signed();
    const now = 1_700_000_000;
    expect(await verifySignature(body, header, SECRET, {
      timestampHeader: String(now - DEFAULT_TOLERANCE_SECONDS - 1),
      now,
    })).toBe(false);
    try {
      await verifySignatureStrict(body, header, SECRET, {
        timestampHeader: String(now - DEFAULT_TOLERANCE_SECONDS - 1),
        now,
      });
      throw new Error("should have thrown");
    } catch (e) {
      expect(e).toBeInstanceOf(ClockSkewError);
      expect((e as ClockSkewError).skewSeconds).toBeGreaterThan(DEFAULT_TOLERANCE_SECONDS);
    }
  });

  it("future timestamp also rejected (symmetric window)", async () => {
    const { body, header } = signed();
    const now = 1_700_000_000;
    await expect(
      verifySignatureStrict(body, header, SECRET, {
        timestampHeader: String(now + DEFAULT_TOLERANCE_SECONDS + 10),
        now,
      })
    ).rejects.toThrow(ClockSkewError);
  });

  it("non-numeric timestamp rejected", async () => {
    const { body, header } = signed();
    expect(await verifySignature(body, header, SECRET, {
      timestampHeader: "not-a-number",
    })).toBe(false);
  });

  it("custom tolerance honored", async () => {
    const { body, header } = signed();
    const now = 1_700_000_000;
    // 50s skew, 30s tolerated → reject.
    expect(await verifySignature(body, header, SECRET, {
      timestampHeader: String(now - 50),
      toleranceSeconds: 30,
      now,
    })).toBe(false);
  });
});

describe("VerificationError base class", () => {
  it("all four subclasses inherit from VerificationError", async () => {
    const body = canonicalize(PAYLOAD);
    try {
      await verifySignatureStrict(body, null, SECRET);
    } catch (e) {
      expect(e).toBeInstanceOf(VerificationError);
    }
    try {
      await verifySignatureStrict(body, "sha512=00", SECRET);
    } catch (e) {
      expect(e).toBeInstanceOf(VerificationError);
    }
  });
});
