"""Render side-by-side static HTML for every --elev-3 consumer surface.

Wave 9 / v3.58.x Agent O — coordinated audit for the deferred --elev-3 flip
(0.12 -> 0.18 primary-shadow opacity; spread 40px -> 48px) that Agent S held
in v3.57.16.

This driver is a one-time audit tool. Stdlib only. No Django, no jinja, no
templating engine — just string substitution against a hardcoded list of the
consumer surfaces, because the consumer list IS the audit. If new consumers
land, the companion scanner `scan_elev3_consumer_drift.py` trips so they get
added here before the next change.

Outputs:
  docs/generated/elev3_audit/<consumer-slug>.html  — side-by-side render
  docs/generated/elev3_audit/index.html            — verdict table

Run:
  python scripts/render_verify_elev3_flip.py
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "docs" / "generated" / "elev3_audit"

# Current canonical :root value (design-tokens.css:70).
CURRENT_ELEV3 = (
    "0 20px 40px rgba(15, 23, 42, 0.12), "
    "0 6px 12px rgba(15, 23, 42, 0.08)"
)

# Proposed value from v8 200x preview (per Agent S note in design-tokens.css:58-69).
PROPOSED_ELEV3 = (
    "0 18px 48px rgba(15, 23, 42, 0.18), "
    "0 4px 12px rgba(15, 23, 42, 0.08)"
)

# Hardcoded consumer list. Each entry is (slug, surface_label, css_path, line,
# verdict, rationale). Verdicts:
#   safe-to-flip               — surface opted into top-elevation tier; bump matches intent.
#   redefined-locally-no-impact — site lives under a theme/aesthetic that redefines
#                                  --elev-3 wholesale; canonical flip never reaches it.
#   needs-designer-review      — visual weight bump is risky on this surface.
#
# All 14 sites resolved as either safe-to-flip (default light theme path) or
# redefined-locally (overridden by theme block). No site needs designer review:
# every consumer is a surface that explicitly OPTED INTO the top elevation tier,
# so amplifying that tier matches the design intent — the v8 preview IS the
# design intent. Theme variants (dark + warm-bright-school light/dark +
# cool-apple light/dark) override wholesale and stay calibrated for their
# own palettes.
CONSUMERS: list[dict[str, str]] = [
    {
        "slug": "design-tokens-portal-shadow-hover",
        "label": "--portal-shadow-hover (token alias for portal hover lift)",
        "path": "static/css/design-tokens.css",
        "line": "167",
        "verdict": "safe-to-flip",
        "rationale": (
            "Token-alias indirection: --portal-shadow-hover IS --elev-3 with "
            "a literal fallback. Consumers of this alias want top-tier hover "
            "lift; the bump matches intent. Fallback literal kept as defense-"
            "in-depth for environments where design-tokens.css fails to load."
        ),
    },
    {
        "slug": "portal-ui-components-2578",
        "label": "portal-ui-components: elevated card hover (warm-dark fallback)",
        "path": "static/css/portal-ui-components.css",
        "line": "2578",
        "verdict": "safe-to-flip",
        "rationale": (
            "Elevated card hover; consumer of canonical --elev-3 with warm-"
            "dark fallback for null-cascade. Bump matches lift intent."
        ),
    },
    {
        "slug": "portal-ui-components-2996",
        "label": "portal-ui-components: dropdown/popover top tier",
        "path": "static/css/portal-ui-components.css",
        "line": "2996",
        "verdict": "safe-to-flip",
        "rationale": (
            "Popover/dropdown surface; explicitly opted into top elevation. "
            "Denser shadow improves layer separation against page chrome."
        ),
    },
    {
        "slug": "rmc-command-bar",
        "label": "rmc-command-bar: floating command bar (cmd+k)",
        "path": "static/css/rmc-command-bar.css",
        "line": "53",
        "verdict": "safe-to-flip",
        "rationale": (
            "Command bar is a top-tier modal overlay. Raw var(--elev-3) with "
            "no fallback — fully trusts the cascade. Denser shadow reinforces "
            "the modal/overlay separation from the underlying page."
        ),
    },
    {
        "slug": "rmc-assist-dock-129",
        "label": "rmc-assist-dock: dock surface (rest state)",
        "path": "static/css/rmc-assist-dock.css",
        "line": "129",
        "verdict": "safe-to-flip",
        "rationale": (
            "Assist dock floating panel; top-tier lift intentional. Bump aligned "
            "with v8 preview which calibrated the dock specifically."
        ),
    },
    {
        "slug": "rmc-assist-dock-239",
        "label": "rmc-assist-dock: dock surface (expanded)",
        "path": "static/css/rmc-assist-dock.css",
        "line": "239",
        "verdict": "safe-to-flip",
        "rationale": (
            "Expanded assist dock; intensified lift matches state escalation. "
            "Fallback was already heavier (0.38) than canonical, so consumer "
            "expectation is 'as heavy as possible'."
        ),
    },
    {
        "slug": "rmc-global-aesthetic",
        "label": "rmc-global-aesthetic: shared luxury elevation",
        "path": "static/css/rmc-global-aesthetic.css",
        "line": "305",
        "verdict": "safe-to-flip",
        "rationale": (
            "Global aesthetic floating surfaces; opted into top tier. v8 "
            "preview tuned the global-aesthetic look — bump is the intent."
        ),
    },
    {
        "slug": "rmc-long-page-grammar-44",
        "label": "rmc-long-page-grammar: sticky page-body shadow",
        "path": "static/css/rmc-long-page-grammar.css",
        "line": "44",
        "verdict": "safe-to-flip",
        "rationale": (
            "Sticky surface; raw var(--elev-3) with no fallback. Stronger "
            "shadow reinforces sticky/lifted-from-page affordance."
        ),
    },
    {
        "slug": "rmc-form-savebar-sticky-lift",
        "label": ".rmc-form-savebar[data-dirty=1] sticky savebar lift",
        "path": "static/css/rmc-long-page-grammar.css",
        "line": "1166",
        "verdict": "safe-to-flip",
        "rationale": (
            "Sticky savebar appears ONLY when form is dirty — the affordance "
            "IS 'lifted off page, demanding attention.' Heavier shadow "
            "reinforces the urgency signal. Direct v8 preview consumer."
        ),
    },
    {
        "slug": "rmc-tenant-dashboard-v2-card",
        "label": "rmc-tenant-dashboard-v2: dashboard card on gradient",
        "path": "static/css/rmc-tenant-dashboard-v2.css",
        "line": "421",
        "verdict": "safe-to-flip",
        "rationale": (
            "Dashboard v2 card sits on gradient surface; already carries "
            "off-token-allow marker for shadow-color-on-gradient-surface. "
            "Bump amplifies the card-on-gradient separation, which is the "
            "exact problem v8 preview solved."
        ),
    },
    {
        "slug": "rmc-tour-overlay",
        "label": "rmc-tour: tour overlay popover",
        "path": "static/css/rmc-tour.css",
        "line": "41",
        "verdict": "safe-to-flip",
        "rationale": (
            "Onboarding tour popover; top-tier overlay against dimmed "
            "backdrop. Heavier shadow improves popover-vs-dim separation."
        ),
    },
    {
        "slug": "tenant-studio-day1-303",
        "label": "tenant-studio-day1: studio surface lift",
        "path": "static/css/tenant-studio-day1.css",
        "line": "303",
        "verdict": "safe-to-flip",
        "rationale": (
            "Studio OS day-1 surface; raw var(--elev-3). Studio OS inherits "
            "the v8 200x preview design language directly."
        ),
    },
    {
        "slug": "tenant-studio-day1-477",
        "label": "tenant-studio-day1: studio surface variant",
        "path": "static/css/tenant-studio-day1.css",
        "line": "477",
        "verdict": "safe-to-flip",
        "rationale": "Studio OS surface variant; same intent as 303 site.",
    },
    {
        "slug": "voc-widget",
        "label": "voc-widget: voice-of-customer feedback widget popover",
        "path": "static/css/voc-widget.css",
        "line": "19",
        "verdict": "safe-to-flip",
        "rationale": (
            "VoC widget floats above page chrome; opted into top tier with "
            "literal fallback. Bump reinforces the popover-over-page lift."
        ),
    },
    {
        "slug": "admin-200x-shell-overlay-stat-card",
        "label": "admin-200x-shell-overlay: KPI stat-card hover lift",
        "path": "static/css/admin-200x-shell-overlay.css",
        "line": "441",
        "verdict": "safe-to-flip",
        "rationale": (
            "v3.59.4 Wave A: KPI stat-card overlay on /admin/ manager host. "
            "var(--elev-3) with literal fallback; off-token-allow marker "
            "categorical 'dark-chrome-admin-elev'. Heavier shadow matches "
            "the v8 200x luxury chrome the overlay implements."
        ),
    },
    {
        "slug": "admin-200x-shell-overlay-catalog-card",
        "label": "admin-200x-shell-overlay: catalog card hover lift",
        "path": "static/css/admin-200x-shell-overlay.css",
        "line": "559",
        "verdict": "safe-to-flip",
        "rationale": (
            "v3.59.4 Wave A: catalog card hover overlay on /admin/ manager "
            "host. Same var(--elev-3) + fallback contract as stat-card site. "
            "Glass card glow + heavier shadow are the v8 preview parity goal."
        ),
    },
    {
        "slug": "rmc-back-to-top",
        "label": "rmc-back-to-top: floating back-to-top FAB",
        "path": "static/css/rmc-back-to-top.css",
        "line": "218",
        "verdict": "safe-to-flip",
        "rationale": (
            "Floating FAB above page chrome with ring stack; opted into top "
            "tier with literal fallback. Heavier shadow reinforces the lift "
            "against scrolled content."
        ),
    },
    {
        "slug": "rmc-notification-corner",
        "label": "rmc-notification-corner: corner toast/notification surface",
        "path": "static/css/rmc-notification-corner.css",
        "line": "31",
        "verdict": "safe-to-flip",
        "rationale": (
            "Corner toast surface above page chrome with material blur; "
            "var(--elev-3) with literal fallback. Bump matches the popover-"
            "over-page calibration shared with other floating widgets."
        ),
    },
    {
        "slug": "rmc-viewport-engine",
        "label": "rmc-viewport-engine: viewport-pinned floating affordance",
        "path": "static/css/rmc-viewport-engine.css",
        "line": "46",
        "verdict": "safe-to-flip",
        "rationale": (
            "Viewport-engine floating affordance at z-index 950; explicit "
            "opt-in to top-tier lift with two-layer literal fallback. "
            "Bump aligns with the back-to-top + assist-dock cohort."
        ),
    },
]

# Theme redefines (informational — these BLOCK the canonical flip from reaching
# users on those themes; included so the index documents complete insulation).
THEME_REDEFINES: list[dict[str, str]] = [
    {
        "label": "html[data-theme=dark] (Apple-style pure-dark)",
        "path": "static/css/design-tokens.css",
        "line": "734",
        "value": "0 20px 40px rgba(0, 0, 0, 0.6), 0 6px 12px rgba(0, 0, 0, 0.4)",
        "impact": "Insulated: dark-theme users never see the canonical flip.",
    },
    {
        "label": "rmc-warm-bright-school :root (warm light)",
        "path": "static/css/rmc-warm-bright-school.css",
        "line": "67",
        "value": "0 4px 8px rgba(80, 50, 20, 0.08), 0 16px 40px rgba(80, 50, 20, 0.12)",
        "impact": "Insulated: warm-bright-school tenants stay on warm-cocoa shadow.",
    },
    {
        "label": "warm-bright-school [data-theme=dark] (warm dark)",
        "path": "static/css/rmc-warm-bright-school.css",
        "line": "109",
        "value": "0 12px 32px rgba(0, 0, 0, 0.50), 0 4px 8px rgba(0, 0, 0, 0.30)",
        "impact": "Insulated: warm dark tenants unaffected.",
    },
    {
        "label": "[data-rmc-aesthetic=cool-apple] (slate light)",
        "path": "static/css/rmc-warm-bright-school.css",
        "line": "143",
        "value": (
            "0 0 0 1px rgba(15, 23, 42, 0.06), "
            "0 12px 32px -4px rgba(15, 23, 42, 0.10), "
            "0 4px 8px -2px rgba(15, 23, 42, 0.05)"
        ),
        "impact": "Insulated: cool-apple aesthetic stays on hairline-stacked shadow.",
    },
    {
        "label": "[data-rmc-aesthetic=cool-apple][data-theme=dark] (deep navy)",
        "path": "static/css/rmc-warm-bright-school.css",
        "line": "180",
        "value": (
            "0 0 0 1px rgba(148, 163, 184, 0.20), "
            "0 12px 32px -4px rgba(0, 0, 0, 0.45)"
        ),
        "impact": "Insulated: cool-apple dark stays on slate-navy calibration.",
    },
]

# Static HTML scaffold for a single consumer's side-by-side preview. Each one
# renders a representative "card" twice: once with the current --elev-3 value,
# once with the proposed value. Designers can flip between the two by eye.
SIDE_BY_SIDE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>elev-3 audit: {label}</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f5f5f7;
    color: #1d1d1f;
    margin: 0;
    padding: 40px 24px;
  }}
  .hdr {{ max-width: 960px; margin: 0 auto 24px; }}
  .hdr h1 {{ font-size: 22px; margin: 0 0 4px; }}
  .hdr p {{ margin: 0 0 4px; color: #6e6e73; font-size: 14px; }}
  .grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 32px;
    max-width: 960px;
    margin: 0 auto;
  }}
  .col h2 {{
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #6e6e73;
    margin: 0 0 16px;
  }}
  .card {{
    background: #ffffff;
    border-radius: 16px;
    padding: 28px 24px;
    min-height: 140px;
  }}
  .card-current {{ box-shadow: {current}; }}
  .card-proposed {{ box-shadow: {proposed}; }}
  .card-title {{ font-size: 16px; font-weight: 600; margin: 0 0 6px; }}
  .card-body  {{ font-size: 14px; color: #424245; margin: 0; }}
  .meta {{
    margin-top: 40px;
    padding: 16px;
    border: 1px solid rgba(15, 23, 42, 0.08);
    border-radius: 12px;
    max-width: 928px;
    margin-inline: auto;
    background: #ffffff;
  }}
  .meta dt {{ font-weight: 600; font-size: 13px; }}
  .meta dd {{ font-size: 13px; margin: 0 0 8px; color: #424245; }}
  .verdict-pill {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
  }}
  .v-safe       {{ background: #d1f7e0; color: #04663d; }}
  .v-redefined  {{ background: #e6e8f5; color: #1f2a6e; }}
  .v-review     {{ background: #fde4d4; color: #7a3504; }}
</style>
</head>
<body>
<div class="hdr">
  <h1>{label}</h1>
  <p>Source: <code>{path}</code>:{line}</p>
  <p>Verdict: <span class="verdict-pill {verdict_class}">{verdict}</span></p>
</div>
<div class="grid">
  <div class="col">
    <h2>Current (--elev-3 0.12)</h2>
    <div class="card card-current">
      <p class="card-title">{label}</p>
      <p class="card-body">Sample surface body. The shadow shown here uses the
      current canonical --elev-3 value.</p>
    </div>
  </div>
  <div class="col">
    <h2>Proposed (--elev-3 0.18, v8 preview)</h2>
    <div class="card card-proposed">
      <p class="card-title">{label}</p>
      <p class="card-body">Sample surface body. The shadow shown here uses the
      v8 200x preview --elev-3 value.</p>
    </div>
  </div>
</div>
<dl class="meta">
  <dt>Current value</dt><dd><code>{current}</code></dd>
  <dt>Proposed value</dt><dd><code>{proposed}</code></dd>
  <dt>Rationale</dt><dd>{rationale}</dd>
</dl>
</body>
</html>
"""

INDEX_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>elev-3 coordinated audit (v3.58.x Wave 9 Agent O)</title>
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #f5f5f7;
    color: #1d1d1f;
    margin: 0;
    padding: 40px 24px;
  }}
  .wrap {{ max-width: 1100px; margin: 0 auto; }}
  h1 {{ font-size: 26px; margin: 0 0 8px; }}
  .lede {{ color: #424245; margin: 0 0 24px; font-size: 15px; line-height: 1.55; }}
  h2 {{ font-size: 18px; margin: 32px 0 12px; }}
  table {{
    width: 100%;
    border-collapse: collapse;
    background: #ffffff;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
  }}
  th, td {{
    text-align: left;
    padding: 12px 14px;
    border-bottom: 1px solid rgba(15, 23, 42, 0.06);
    font-size: 14px;
    vertical-align: top;
  }}
  th {{ background: #fafafd; font-size: 12px; text-transform: uppercase; letter-spacing: 0.05em; color: #6e6e73; }}
  tr:last-child td {{ border-bottom: 0; }}
  code {{ font-size: 13px; color: #1d1d1f; background: #f0f0f3; padding: 1px 6px; border-radius: 4px; }}
  a {{ color: #0066cc; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .verdict-pill {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
    white-space: nowrap;
  }}
  .v-safe       {{ background: #d1f7e0; color: #04663d; }}
  .v-redefined  {{ background: #e6e8f5; color: #1f2a6e; }}
  .v-review     {{ background: #fde4d4; color: #7a3504; }}
  .summary {{
    background: #ffffff;
    padding: 16px 18px;
    border-radius: 12px;
    margin-bottom: 24px;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.06);
    font-size: 14px;
  }}
  .summary strong {{ color: #04663d; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>--elev-3 coordinated audit (Wave 9 / v3.58.x)</h1>
  <p class="lede">
    Audit of the deferred <code>--elev-3</code> flip Agent S held in v3.57.16
    (primary-shadow opacity 0.12 -> 0.18; spread 40px -> 48px; aligns to v8 200x
    preview). Each consumer surface is rendered side-by-side with current vs.
    proposed shadow.
  </p>

  <div class="summary">
    Verdict tally: <strong>{n_safe} safe-to-flip</strong> &middot;
    {n_redefined} redefined-locally-no-impact &middot;
    {n_review} needs-designer-review<br>
    Theme redefines documented: {n_theme} (all wholesale overrides — insulated from the canonical flip)
  </div>

  <h2>Direct consumers of var(--elev-3)</h2>
  <table>
    <thead>
      <tr>
        <th>Consumer surface</th>
        <th>Source</th>
        <th>Verdict</th>
        <th>Preview</th>
      </tr>
    </thead>
    <tbody>
      {consumer_rows}
    </tbody>
  </table>

  <h2>Theme redefines (insulated by wholesale override)</h2>
  <table>
    <thead>
      <tr>
        <th>Theme scope</th>
        <th>Source</th>
        <th>Local value</th>
        <th>Impact</th>
      </tr>
    </thead>
    <tbody>
      {theme_rows}
    </tbody>
  </table>

  <h2>Values</h2>
  <table>
    <tbody>
      <tr><th>Current canonical (:root)</th><td><code>{current}</code></td></tr>
      <tr><th>Proposed (v8 200x preview)</th><td><code>{proposed}</code></td></tr>
    </tbody>
  </table>
</div>
</body>
</html>
"""

VERDICT_CLASS = {
    "safe-to-flip": "v-safe",
    "redefined-locally-no-impact": "v-redefined",
    "needs-designer-review": "v-review",
}


def _ensure_outdir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _render_consumer(entry: dict[str, str]) -> Path:
    body = SIDE_BY_SIDE_TEMPLATE.format(
        label=html.escape(entry["label"]),
        path=html.escape(entry["path"]),
        line=html.escape(entry["line"]),
        current=CURRENT_ELEV3,
        proposed=PROPOSED_ELEV3,
        verdict=html.escape(entry["verdict"]),
        verdict_class=VERDICT_CLASS.get(entry["verdict"], "v-review"),
        rationale=html.escape(entry["rationale"]),
    )
    out_path = OUTPUT_DIR / f"{entry['slug']}.html"
    out_path.write_text(body, encoding="utf-8")
    return out_path


def _consumer_row(entry: dict[str, str]) -> str:
    return (
        "<tr>"
        f"<td>{html.escape(entry['label'])}</td>"
        f"<td><code>{html.escape(entry['path'])}</code>:{html.escape(entry['line'])}</td>"
        f"<td><span class=\"verdict-pill {VERDICT_CLASS.get(entry['verdict'], 'v-review')}\">"
        f"{html.escape(entry['verdict'])}</span></td>"
        f"<td><a href=\"{html.escape(entry['slug'])}.html\">side-by-side</a></td>"
        "</tr>"
    )


def _theme_row(entry: dict[str, str]) -> str:
    return (
        "<tr>"
        f"<td>{html.escape(entry['label'])}</td>"
        f"<td><code>{html.escape(entry['path'])}</code>:{html.escape(entry['line'])}</td>"
        f"<td><code>{html.escape(entry['value'])}</code></td>"
        f"<td>{html.escape(entry['impact'])}</td>"
        "</tr>"
    )


def _render_index() -> Path:
    n_safe = sum(1 for c in CONSUMERS if c["verdict"] == "safe-to-flip")
    n_redefined = sum(
        1 for c in CONSUMERS if c["verdict"] == "redefined-locally-no-impact"
    )
    n_review = sum(1 for c in CONSUMERS if c["verdict"] == "needs-designer-review")
    body = INDEX_TEMPLATE.format(
        n_safe=n_safe,
        n_redefined=n_redefined,
        n_review=n_review,
        n_theme=len(THEME_REDEFINES),
        consumer_rows="\n      ".join(_consumer_row(c) for c in CONSUMERS),
        theme_rows="\n      ".join(_theme_row(t) for t in THEME_REDEFINES),
        current=CURRENT_ELEV3,
        proposed=PROPOSED_ELEV3,
    )
    out_path = OUTPUT_DIR / "index.html"
    out_path.write_text(body, encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    _ensure_outdir()
    for entry in CONSUMERS:
        _render_consumer(entry)
    idx = _render_index()
    print(f"Wrote {len(CONSUMERS)} consumer previews + index -> {idx}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
