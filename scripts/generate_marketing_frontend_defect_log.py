#!/usr/bin/env python3
"""Write docs/generated/marketing_frontend_defect_log.md (prompt deliverable #1)."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT_MD = REPO / "docs" / "generated" / "marketing_frontend_defect_log.md"
OUT_JSON = REPO / "docs" / "generated" / "marketing_frontend_defect_log.json"
MANIFEST = REPO / "static" / "marketing" / "css" / "marketing-bundles.manifest.json"

DEFECTS = [
    {
        "id": "P1",
        "severity": "critical",
        "category": "CWV / speed",
        "finding": "32 synchronous render-blocking stylesheets on every marketing page",
        "remediation": "marketing-critical.min.css + deferred marketing-enhanced.min.css; 4 blocking links in base_marketing.html",
        "status": "fixed",
    },
    {
        "id": "P2",
        "severity": "high",
        "category": "CWV / speed",
        "finding": "Blocking Google Fonts CDN without self-hosted preload path",
        "remediation": "Self-hosted Source Serif 4 WOFF2 + marketing-fonts.css in critical bundle",
        "status": "fixed",
    },
    {
        "id": "P3",
        "severity": "high",
        "category": "CWV / speed",
        "finding": "Portal-only JS on acquisition traffic (lexicon, friction, launch splash)",
        "remediation": "Removed from base_marketing.html; hero video JS homepage-only",
        "status": "fixed",
    },
    {
        "id": "T1",
        "severity": "critical",
        "category": "theme",
        "finding": "Split theme bootstraps caused FOUC and v2 data-theme=system no-op",
        "remediation": "mkt-theme-bootstrap.js + v3 effective data-theme contract",
        "status": "fixed",
    },
    {
        "id": "T2",
        "severity": "high",
        "category": "theme / contrast",
        "finding": "Hardcoded colors below AAA on dark marketing chrome",
        "remediation": "tokens-marketing.css SOT + marketing-accessibility-hardening.css (in critical bundle) + marketing-theme-contrast.spec.js axe critical gate",
        "status": "fixed",
    },
    {
        "id": "C1",
        "severity": "medium",
        "category": "conversion",
        "finding": "Contact/demo forms lacked inline validation hook",
        "remediation": "novalidate data-rmc-validate=inline + rmc-form-validation.js",
        "status": "fixed",
    },
    {
        "id": "S1",
        "severity": "high",
        "category": "SEO",
        "finding": "Duplicate JSON-LD blocks across page templates",
        "remediation": "Central mkt_structured_data.html in base_marketing.html",
        "status": "fixed",
    },
    {
        "id": "S2",
        "severity": "medium",
        "category": "SEO",
        "finding": "Missing canonical/OG wiring on some marketing pages",
        "remediation": "rmc_social_meta.html + canonical_url in base; verify_marketing_seo_shell.py",
        "status": "fixed",
    },
    {
        "id": "H1",
        "severity": "medium",
        "category": "hero / media",
        "finding": "Hero video referenced but not shipped; MP4 gitignored",
        "remediation": "hero-home.mp4 + poster + setup_marketing_ci_assets.py + gitignore exceptions",
        "status": "fixed",
    },
    {
        "id": "B1",
        "severity": "medium",
        "category": "budget",
        "finding": "Original ~40KB critical CSS target not met with full grammar + shell",
        "remediation": "marketing-critical-path.css + deferred grammar/narrative/full shell in enhanced; critical_max 45000 enforced",
        "status": "fixed",
    },
    {
        "id": "I1",
        "severity": "high",
        "category": "UX / impact",
        "finding": "Bell timeline + persona tabs showed full-screen dashboards with low narrative impact",
        "remediation": "Single-panel bell clock + constrained mkt-v3-dashboard-frame--impact + story metric column",
        "status": "fixed",
    },
    {
        "id": "I2",
        "severity": "high",
        "category": "UX / contrast",
        "finding": "World map labels used #1F2937 on cinematic dark background (illegible / blurred)",
        "remediation": "mkt-world-map currentColor labels + HTML caption block + marketing-impact.css cinematic tokens",
        "status": "fixed",
    },
    {
        "id": "I3",
        "severity": "medium",
        "category": "conversion",
        "finding": "Hero lacked live simulated campus dashboard (prompt live-campus pulse)",
        "remediation": "_hero_live_campus_pulse.html + mkt-live-campus-pulse.js SVG/CSS animations",
        "status": "fixed",
    },
    {
        "id": "I4",
        "severity": "medium",
        "category": "media",
        "finding": "Walkthrough lacked accessible glass video portal with play/pause",
        "remediation": "_video_portal.html + mkt-video-portal.js on marketing_landing_v2.html",
        "status": "fixed",
    },
    {
        "id": "I5",
        "severity": "medium",
        "category": "IA / lanes",
        "finding": "No short routes or lane-aware chrome accents for academics/admissions/finance",
        "remediation": "/academics/ /admissions/ /finance/ redirects + mkt-lane-chrome.js + lane tokens in tokens-marketing.css",
        "status": "fixed",
    },
    {
        "id": "I6",
        "severity": "low",
        "category": "i18n",
        "finding": "Pricing matrix could clip on verbose locales",
        "remediation": "marketing-impact.css table-layout fixed + overflow-wrap anywhere on mkt-v3-pricing-matrix",
        "status": "fixed",
    },
    {
        "id": "Q1",
        "severity": "high",
        "category": "Sweep 2 QA",
        "finding": "Responsive impact sections not gated for horizontal scroll on mobile",
        "remediation": "tests/e2e/marketing-impact-responsive.spec.js + verify_marketing_sweep2.py",
        "status": "fixed",
    },
    {
        "id": "G1",
        "severity": "high",
        "category": "production proof",
        "finding": "No automated smoke for deployed marketing + lane routes",
        "remediation": "scripts/verify_marketing_production_smoke.py (PRODUCTION_BASE_URL) + Sweep 2 LCP/CLS when MKT_RUN_SWEEP2_LIVE=1",
        "status": "fixed",
    },
    {
        "id": "G2",
        "severity": "high",
        "category": "lane UX",
        "finding": "Academics/admissions/finance lanes shared generic archetype layout",
        "remediation": "_lane_academics_matrix.html + _lane_admissions_steps.html + _lane_finance_ledger.html + marketing-gear2-lanes.css",
        "status": "fixed",
    },
    {
        "id": "G3",
        "severity": "high",
        "category": "homepage motion",
        "finding": "Bell and persona sections duplicated; no auto-advance; static globe",
        "remediation": "_day_role_story.html + data-bell-auto-ms + mkt-globe-tooltips.js + scroll-narrative keyboard/auto",
        "status": "fixed",
    },
    {
        "id": "G4",
        "severity": "medium",
        "category": "geo",
        "finding": "Hero ignored visitor country; empty _hero_by_country map",
        "remediation": "apps/schools/marketing_geo.py + _hero_geo_subline.html + country headlines in _marketing_context",
        "status": "fixed",
    },
    {
        "id": "G5",
        "severity": "medium",
        "category": "conversion",
        "finding": "No illustrative trust strip or ROI proof quote on homepage",
        "remediation": "marketing_carousel_items logo strip + _proof_quote.html in ROI panel",
        "status": "fixed",
    },
    {
        "id": "G6",
        "severity": "high",
        "category": "a11y / i18n",
        "finding": "Gear-up a11y/i18n not gated after day|role toggle refactor",
        "remediation": "marketing-gear2-a11y.spec.js + marketing-pricing-i18n.spec.js + impact-responsive day|role flow",
        "status": "fixed",
    },
    {
        "id": "G7",
        "severity": "low",
        "category": "architecture",
        "finding": "Risk of parallel Next.js marketing app duplicating Django stack",
        "remediation": "Explicit Django-only delivery; verify_marketing_gear2_completion.py in audit_marketing_frontend_100",
        "status": "fixed",
    },
]


def _bundle_bytes() -> dict[str, int]:
    if not MANIFEST.is_file():
        return {}
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {
        "critical_bytes": int(data.get("critical", {}).get("bytes", 0)),
        "enhanced_bytes": int(data.get("enhanced", {}).get("bytes", 0)),
    }


def render_md() -> str:
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    bundles = _bundle_bytes()
    lines = [
        "# Marketing frontend conversion defect log",
        "",
        f"- **Generated:** `{ts}`",
        "- **Surface:** runmycampus.com public marketing (Django templates + static/marketing/)",
        "- **Wave:** v3.35.3 + v3.37.1 impact + v3.37.2 gear-up — see `docs/CSS_RETIREMENT_DOCKET.md`",
        "",
        "## Bundle metrics (post-fix)",
        "",
        f"- Critical min.css: **{bundles.get('critical_bytes', 0):,}** bytes",
        f"- Enhanced min.css: **{bundles.get('enhanced_bytes', 0):,}** bytes (deferred)",
        "",
        "## Defect register",
        "",
        "| ID | Severity | Category | Status | Finding | Remediation |",
        "|----|----------|----------|--------|---------|-------------|",
    ]
    for d in DEFECTS:
        note = d.get("note", "")
        rem = d["remediation"] + (f" ({note})" if note else "")
        lines.append(
            f"| {d['id']} | {d['severity']} | {d['category']} | {d['status']} | {d['finding']} | {rem} |"
        )
    lines.extend(
        [
            "",
            "## Prompt deliverable mapping",
            "",
            "| Deliverable | Repo artifact |",
            "|-------------|---------------|",
            "| 1. Defect log | This file + `.json` sibling |",
            "| 2. Production rewrite | `base_marketing.html`, bundles, theme/hero partials |",
            "| 3. Sweep 2 QA | `tests/e2e/marketing-theme-contrast.spec.js`, `verify_marketing_lighthouse_budget.*` |",
            "| 4. SOT tokens | `static/marketing/css/tokens-marketing.css` |",
            "| 5. Impact layer | `marketing-impact.css`, bell/persona/globe/hero/lane partials + `verify_marketing_impact_layer.py` |",
            "| 6. Gear-up 1–7 | `verify_marketing_gear2_completion.py`, lane/home partials, geo + production smoke |",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="Write docs/generated artifacts")
    args = parser.parse_args()
    if not args.write:
        print("Pass --write to emit docs/generated/marketing_frontend_defect_log.{md,json}")
        return 0
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(render_md(), encoding="utf-8")
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "defects": DEFECTS,
        "bundles": _bundle_bytes(),
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"generate_marketing_frontend_defect_log: wrote {OUT_MD.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
