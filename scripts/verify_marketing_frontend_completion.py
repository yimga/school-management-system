#!/usr/bin/env python3
"""Repo-contained checklist gate for marketing frontend prompt completion (v3.35.3)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "scripts/marketing_css_bundle_manifest.json",
    "scripts/build_marketing_css_bundles.py",
    "scripts/verify_marketing_css_bundles_fresh.py",
    "scripts/verify_marketing_public_shell.py",
    "scripts/verify_marketing_hero_media.py",
    "scripts/verify_marketing_lighthouse_budget.py",
    "scripts/verify_marketing_lighthouse_budget.mjs",
    "scripts/setup_marketing_ci_assets.py",
    "scripts/fetch_marketing_hero_media.py",
    "scripts/fetch_marketing_fonts.py",
    "static/marketing/css/marketing-critical-path.css",
    "static/marketing/css/marketing-critical.min.css",
    "static/marketing/css/marketing-enhanced.min.css",
    "static/marketing/js/mkt-theme-bootstrap.js",
    "static/marketing/js/theme-toggle.js",
    "templates/marketing/base_marketing.html",
    "templates/marketing/components/_hero_home_video.html",
    "templates/marketing/partials/mkt_structured_data.html",
    "tests/e2e/marketing-theme-contrast.spec.js",
    ".github/workflows/marketing-gates.yml",
    "scripts/verify_marketing_seo_shell.py",
    "scripts/generate_marketing_frontend_defect_log.py",
    "docs/generated/marketing_frontend_defect_log.md",
    "static/marketing/css/marketing-impact.css",
    "static/marketing/js/mkt-live-campus-pulse.js",
    "static/marketing/js/mkt-video-portal.js",
    "static/marketing/js/mkt-lane-chrome.js",
    "templates/marketing/components/_hero_live_campus_pulse.html",
    "templates/marketing/components/_video_portal.html",
    "scripts/verify_marketing_impact_layer.py",
    "scripts/verify_marketing_sweep2.py",
    "tests/e2e/marketing-impact-responsive.spec.js",
    "scripts/verify_marketing_gear2_completion.py",
    "static/marketing/css/marketing-gear2-home.css",
    "static/marketing/css/marketing-gear2-lanes.css",
    "apps/schools/marketing_geo.py",
    "tests/e2e/marketing-gear2-a11y.spec.js",
    "tests/e2e/marketing-pricing-i18n.spec.js",
)

SUBPROCESS_GATES = (
    "scripts/setup_marketing_ci_assets.py",
    "scripts/verify_marketing_css_bundles_fresh.py",
    "scripts/verify_marketing_public_shell.py",
    "scripts/verify_marketing_hero_media.py",
    "scripts/verify_marketing_impact_layer.py",
    "scripts/verify_marketing_sweep2.py",
    "scripts/verify_marketing_gear2_completion.py",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    errors: list[str] = []

    for rel in REQUIRED_FILES:
        if not (REPO / rel).is_file():
            errors.append(f"missing file: {rel}")

    base = REPO / "templates" / "marketing" / "base_marketing.html"
    if base.is_file():
        text = _read(base)
        if "fonts.googleapis.com" in text or "fonts.gstatic.com" in text:
            errors.append("base_marketing.html still references Google Fonts CDN")
        if "marketing-critical.min.css" not in text:
            errors.append("base_marketing.html missing marketing-critical.min.css")
        if "mkt-theme-bootstrap.js" not in text:
            errors.append("base_marketing.html missing mkt-theme-bootstrap.js")

    contact = REPO / "templates" / "marketing" / "components" / "_marketing_contact_form.html"
    if contact.is_file():
        ct = _read(contact)
        if 'data-rmc-validate="inline"' not in ct:
            errors.append("contact form missing data-rmc-validate=inline")

    demo = REPO / "templates" / "marketing" / "components" / "_marketing_demo_form.html"
    if demo.is_file():
        dt = _read(demo)
        if 'data-rmc-validate="inline"' not in dt:
            errors.append("demo form missing data-rmc-validate=inline")

    docket = REPO / "docs" / "CSS_RETIREMENT_DOCKET.md"
    if docket.is_file():
        docket_text = _read(docket)
        if "v3.35.3" not in docket_text or "marketing frontend completion" not in docket_text.lower():
            errors.append("CSS_RETIREMENT_DOCKET.md missing v3.35.3 marketing wave section")
        if "v3.37.1" not in docket_text or "marketing impact" not in docket_text.lower():
            errors.append("CSS_RETIREMENT_DOCKET.md missing v3.37.1 marketing impact wave section")
        if "v3.37.2" not in docket_text or "gear-up" not in docket_text.lower():
            errors.append("CSS_RETIREMENT_DOCKET.md missing v3.37.2 marketing gear-up wave section")

    sw = REPO / "static" / "js" / "service-worker.js"
    if sw.is_file():
        sw_text = _read(sw)
        if "Marketing frontend completion" not in sw_text:
            errors.append(
                "service-worker.js missing v3.35.3 marketing wave comment (cache bump may be newer)"
            )

    defect_log = REPO / "docs" / "generated" / "marketing_frontend_defect_log.md"
    if not defect_log.is_file():
        errors.append(
            "docs/generated/marketing_frontend_defect_log.md missing (run generate_marketing_frontend_defect_log.py --write)"
        )

    seo_gate = REPO / "scripts" / "verify_marketing_seo_shell.py"
    if not seo_gate.is_file():
        errors.append("scripts/verify_marketing_seo_shell.py missing")
    else:
        proc = subprocess.run(
            [sys.executable, str(seo_gate)],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            errors.append(f"verify_marketing_seo_shell.py failed:\n{proc.stderr or proc.stdout}")

    gitignore = REPO / ".gitignore"
    if gitignore.is_file():
        gi = _read(gitignore)
        if "!static/marketing/video/hero-home.mp4" not in gi:
            errors.append(".gitignore missing hero-home.mp4 allow exception")

    bundle_manifest = REPO / "static" / "marketing" / "css" / "marketing-bundles.manifest.json"
    if bundle_manifest.is_file():
        import json

        data = json.loads(bundle_manifest.read_text(encoding="utf-8"))
        crit_bytes = int(data.get("critical", {}).get("bytes", 0))
        crit_max = int(data.get("budgets", {}).get("critical_max", 45000))
        if crit_bytes > crit_max:
            errors.append(
                f"critical bundle {crit_bytes}B exceeds budget {crit_max}B — rebuild or adjust manifest"
            )

    for rel in SUBPROCESS_GATES:
        proc = subprocess.run(
            [sys.executable, str(REPO / rel)],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            errors.append(f"{rel} failed:\n{proc.stderr or proc.stdout}")

    if errors:
        print("verify_marketing_frontend_completion: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    print("verify_marketing_frontend_completion: OK (prompt checklist satisfied)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
