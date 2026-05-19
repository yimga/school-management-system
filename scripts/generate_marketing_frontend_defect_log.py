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
        "- **Wave:** v3.35.3 — see `docs/CSS_RETIREMENT_DOCKET.md`",
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
