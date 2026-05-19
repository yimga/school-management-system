/**
 * Support AI engine room — code oracle + token manager contracts.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const ROOT = resolve(__dirname, "..");

function read(rel: string): string {
  return readFileSync(resolve(ROOT, rel), "utf-8");
}

describe("engine room modules", () => {
  it("code_oracle reflects live topology", () => {
    const py = read("services/ai/code_oracle.py");
    expect(py).toContain("DynamicSystemInspector");
    expect(py).toContain("build_route_manual_outline");
  });

  it("token_manager re-exports compressor", () => {
    const py = read("services/ai/token_manager.py");
    expect(py).toContain("ContextTokenCompressor");
    expect(py).toContain("estimate_tokens");
  });

  it("gateway caps query length and uses code oracle fallback", () => {
    const py = read("services/ai/gateway.py");
    expect(py).toContain("_MAX_USER_QUERY_CHARS = 8000");
    expect(py).toContain("build_route_manual_outline");
  });
});
