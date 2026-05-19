/**
 * Support pipeline integrity — KB AI panel + escalation contracts (Vitest + jsdom).
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const ROOT = resolve(__dirname, "..");

function read(rel: string): string {
  return readFileSync(resolve(ROOT, rel), "utf-8");
}

describe("support pipeline templates", () => {
  it("KB AI panel wires engine-room API and escalation", () => {
    const html = read("templates/portal/partials/kb_ai_assistant_panel.html");
    expect(html).toContain("data-support-assistant-url");
    expect(html).toContain("api_v1:ai-support-assistant");
    expect(html).toContain("data-rmc-kb-ai-escalate");
    expect(html).toContain("data-rmc-support-error-boundary");
    expect(html).toContain('maxlength="8000"');
  });

  it("operator KB article has breadcrumb trail", () => {
    const html = read("templates/portal/operator/kb_article_body.html");
    expect(html).toContain("manager_help_center");
    expect(html).toContain("kb:kb_home");
    expect(html).toContain('aria-label="breadcrumb"');
  });
});

describe("rmc-kb-ai-assistant.js", () => {
  it("truncates bloated queries and calls support assistant payload", () => {
    const src = read("static/js/rmc-kb-ai-assistant.js");
    expect(src).toContain("MAX_QUERY_CHARS = 8000");
    expect(src).toContain("active_url");
    expect(src).toContain("escalation_required");
    expect(src).toContain("data-support-assistant-url");
  });
});
