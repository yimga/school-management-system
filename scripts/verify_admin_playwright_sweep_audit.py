#!/usr/bin/env python3
"""Admin Playwright sweep audit contract (batch 1617 residual).

Default: accepts render-contract full-crawl evidence when layout Playwright is deferred.
Strict: ADMIN_PLAYWRIGHT_LAYOUT_SWEEP_REQUIRED=1 requires a real layout sweep (failed=0).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/generated/admin_playwright_sweep_audit.json"
RENDER_AUDIT = ROOT / "docs/generated/admin_changelist_render_audit.json"


def main() -> int:
    strict_layout = (os.environ.get("ADMIN_PLAYWRIGHT_LAYOUT_SWEEP_REQUIRED", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    failures: list[str] = []

    if not AUDIT.is_file():
        failures.append(f"missing {AUDIT.relative_to(ROOT)}")
    else:
        data = json.loads(AUDIT.read_text(encoding="utf-8"))
        tier = data.get("sweepTier")
        if tier != "admin_changelist":
            failures.append(f"sweepTier must be admin_changelist (got {tier!r})")
        source = data.get("evidenceSource") or ""
        failed = int(data.get("failed") or 0)
        if strict_layout:
            if source == "admin_changelist_render_contract_full_crawl":
                failures.append(
                    "layout Playwright sweep required but audit is render-contract proxy only"
                )
            if failed != 0:
                failures.append(f"layout sweep failed count {failed} (expected 0)")
            if not data.get("results"):
                failures.append("layout sweep missing per-route results[]")
        else:
            if source == "admin_changelist_render_contract_full_crawl":
                if not RENDER_AUDIT.is_file():
                    failures.append("render proxy audit requires admin_changelist_render_audit.json")
                else:
                    render = json.loads(RENDER_AUDIT.read_text(encoding="utf-8"))
                    if not render.get("full_crawl"):
                        failures.append("render audit must be full_crawl=true")
                    if not render.get("pass"):
                        failures.append("render audit pass=false")
            elif failed != 0:
                failures.append(f"failed={failed} without render-contract proxy")

    if failures:
        print("ADMIN_PLAYWRIGHT_SWEEP_AUDIT_FAIL")
        for msg in failures:
            print(f"  - {msg}")
        return 1

    print("ADMIN_PLAYWRIGHT_SWEEP_AUDIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
