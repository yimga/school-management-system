#!/usr/bin/env python3
"""Gate: marketplace / proof catalog surfaces must have dark-mode chromatic coverage.

Prevents white-on-white App Catalog cards when data-theme/data-resolved-theme is dark.
Repo-native companion to docs/THEME_SYSTEM.md §0 and manager-aesthetic-polish v2.47 block.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "marketplace_proof_surface_dark_completion.json"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    proof_pages = _read("static/marketing/css/proof-pages.css")
    manager = _read("static/css/manager-aesthetic-polish.css")
    readability = _read("static/css/theme-platform-readability.css")
    safety = _read("static/css/dark-mode-safety-net.css")
    impact_js = _read("static/js/_pages/marketplace__partials__install_impact_modal-1.js")

    checks: list[dict[str, str]] = []

    def record(cid: str, ok: bool, detail: str) -> None:
        checks.append({"id": cid, "status": "PASS" if ok else "FAIL", "detail": detail})

    record(
        "proof_pages_semantic_surfaces",
        "color-mix(in srgb, var(--color-base-0)" not in proof_pages
        and "var(--surface-elevated, var(--admin-content-bg" in proof_pages,
        "proof-pages uses semantic elevated surfaces, not --color-base-0 white mix",
    )
    record(
        "proof_app_card_tokens",
        ".proof-app-card" in proof_pages and "var(--color-base-0)" not in proof_pages.split(".proof-app-card")[1].split("}")[0],
        "proof-app-card avoids --color-base-0 fallback",
    )
    record(
        "manager_dark_proof_cards",
        '[data-theme="dark"] #cp-main-content .proof-app-card' in manager
        and '[data-theme="dark"] #cp-main-content .proof-panel' in manager,
        "manager-aesthetic-polish repaints proof catalog cards in dark mode",
    )
    record(
        "readability_dark_tenant_catalog",
        'html[data-resolved-theme="dark"]' in readability
        and ".tenant-app-catalog-wrap" in readability
        and ".proof-app-card" in readability.split(".tenant-app-catalog-wrap")[1],
        "theme-platform-readability dark rules cover tenant app catalog",
    )
    record(
        "safety_net_proof_surfaces",
        ".proof-app-card" in safety and ".rmc-install-impact-graph" in safety,
        "dark-mode-safety-net forces elevated slabs on proof surfaces",
    )
    record(
        "install_impact_no_bg_white",
        "bg-white" not in impact_js or "bg-white rmc-install-impact-graph" not in impact_js,
        "install impact modal graph mount does not inject bg-white",
    )

    failed = [c for c in checks if c["status"] == "FAIL"]
    payload = {
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    for c in checks:
        mark = "OK" if c["status"] == "PASS" else "FAIL"
        print(f"[{mark}] {c['id']}: {c['detail']}")

    if failed:
        print(f"\nMARKETPLACE_PROOF_SURFACE_DARK_FAIL ({len(failed)} checks)")
        return 1
    print("\nMARKETPLACE_PROOF_SURFACE_DARK_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
