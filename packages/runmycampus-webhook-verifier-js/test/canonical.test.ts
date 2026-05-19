/**
 * Canonical-JSON serializer tests + Python-parity fixture verification.
 *
 * If `test_every_case_canonical_bytes_match` fails, the Python and JS
 * twins have drifted byte-for-byte and customers will see signature
 * mismatches that look like tampering.
 */

import { describe, expect, it, beforeAll } from "vitest";
import {
  canonicalize,
  canonicalizeToString,
  CanonicalJSONError,
} from "../src/canonical";
import fs from "node:fs";
import path from "node:path";
import { createHash } from "node:crypto";

interface FixtureCase {
  name: string;
  input: unknown;
  expected_canonical: string;
  expected_sha256: string;
}
interface FixtureFile {
  version: string;
  cases: FixtureCase[];
}

const FIXTURE_PATH = path.join(__dirname, "fixtures", "canonical-cases.json");

function sha256Hex(bytes: Uint8Array): string {
  return createHash("sha256").update(bytes).digest("hex");
}

describe("canonical determinism", () => {
  it("empty object", () => {
    expect(canonicalizeToString({})).toBe("{}");
  });

  it("empty array", () => {
    expect(canonicalizeToString([])).toBe("[]");
  });

  it("dict key order independent", () => {
    const a = canonicalizeToString({ b: 2, a: 1, c: 3 });
    const b = canonicalizeToString({ c: 3, a: 1, b: 2 });
    expect(a).toBe(b);
    expect(a).toBe('{"a":1,"b":2,"c":3}');
  });

  it("nested object keys sorted recursively", () => {
    const out = canonicalizeToString({ outer: { z: 26, a: 1 }, first: "value" });
    expect(out).toBe('{"first":"value","outer":{"a":1,"z":26}}');
  });

  it("no whitespace anywhere", () => {
    const out = canonicalizeToString({ a: [1, 2, { nested: "yes" }] });
    expect(out).not.toContain(" ");
    expect(out).not.toContain("\n");
    expect(out).not.toContain("\t");
  });

  it("unicode emitted literally not escaped", () => {
    const out = canonicalizeToString("学校管理");
    expect(out).not.toContain("\\u");
    expect(JSON.parse(out)).toBe("学校管理");
  });

  it("escaped control chars", () => {
    const out = canonicalizeToString('line1\nline2\t"q"\\b');
    expect(out).toContain("\\n");
    expect(out).toContain("\\t");
    expect(out).toContain('\\"');
    expect(out).toContain("\\\\");
  });

  it("undefined skipped in object", () => {
    const out = canonicalizeToString({ a: 1, b: undefined, c: 3 });
    expect(out).toBe('{"a":1,"c":3}');
  });
});

describe("canonical rejection", () => {
  it("NaN rejected", () => {
    expect(() => canonicalize(NaN)).toThrow(CanonicalJSONError);
  });
  it("+Infinity rejected", () => {
    expect(() => canonicalize(Infinity)).toThrow(CanonicalJSONError);
  });
  it("-Infinity rejected", () => {
    expect(() => canonicalize(-Infinity)).toThrow(CanonicalJSONError);
  });
  it("nested NaN rejected", () => {
    expect(() => canonicalize({ x: [1, 2, NaN] })).toThrow(CanonicalJSONError);
  });
  it("Date rejected", () => {
    expect(() => canonicalize({ x: new Date() })).toThrow(CanonicalJSONError);
  });
});

describe("python-parity fixtures", () => {
  let fixture: FixtureFile;

  beforeAll(() => {
    const raw = fs.readFileSync(FIXTURE_PATH, "utf-8");
    fixture = JSON.parse(raw);
  });

  it("fixture file exists and has at least 12 cases", () => {
    expect(fixture).toBeDefined();
    expect(fixture.cases.length).toBeGreaterThanOrEqual(12);
  });

  it("every case canonical bytes match the python expected_canonical", () => {
    const failures: Array<[string, string, string]> = [];
    for (const c of fixture.cases) {
      const actual = canonicalizeToString(c.input);
      if (actual !== c.expected_canonical) {
        failures.push([c.name, c.expected_canonical, actual]);
      }
    }
    expect(failures).toEqual([]);
  });

  it("every case sha256 of canonical bytes matches the pinned expected_sha256", () => {
    const failures: Array<[string, string, string]> = [];
    for (const c of fixture.cases) {
      const bytes = canonicalize(c.input);
      const actual = sha256Hex(bytes);
      if (actual !== c.expected_sha256) {
        failures.push([c.name, c.expected_sha256, actual]);
      }
    }
    expect(failures).toEqual([]);
  });
});
