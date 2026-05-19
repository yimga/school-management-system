#!/usr/bin/env python3
"""One-shot audit: marketing forensic prompt 100% completion (exit 0 = done)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

STEPS = [
    ("build_marketing_css_bundles.py", [sys.executable, "scripts/build_marketing_css_bundles.py"]),
    ("generate_marketing_frontend_defect_log.py --write", [
        sys.executable,
        "scripts/generate_marketing_frontend_defect_log.py",
        "--write",
    ]),
    ("verify_marketing_seo_shell.py", [sys.executable, "scripts/verify_marketing_seo_shell.py"]),
    ("verify_marketing_frontend_completion.py", [
        sys.executable,
        "scripts/verify_marketing_frontend_completion.py",
    ]),
    ("verify_marketing_css_bundles_fresh.py", [
        sys.executable,
        "scripts/verify_marketing_css_bundles_fresh.py",
    ]),
    ("verify_marketing_public_shell.py", [
        sys.executable,
        "scripts/verify_marketing_public_shell.py",
    ]),
    ("verify_marketing_hero_media.py", [sys.executable, "scripts/verify_marketing_hero_media.py"]),
    (
        "test_marketing_phase1_foundation",
        [sys.executable, "scripts/run_sqlite_memory_tests.py", "apps.schools.tests.test_marketing_phase1_foundation"],
    ),
]


def _defects_all_fixed() -> bool:
    path = REPO / "docs" / "generated" / "marketing_frontend_defect_log.json"
    if not path.is_file():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    for row in data.get("defects", []):
        if row.get("status") not in ("fixed",):
            return False
    return bool(data.get("defects"))


def main() -> int:
    failures: list[str] = []

    for label, cmd in STEPS:
        proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True)
        if proc.returncode != 0:
            failures.append(f"{label}:\n{proc.stderr or proc.stdout}")

    if not _defects_all_fixed():
        failures.append("defect log contains non-fixed rows")

    bundle = REPO / "static" / "marketing" / "css" / "marketing-bundles.manifest.json"
    if bundle.is_file():
        data = json.loads(bundle.read_text(encoding="utf-8"))
        crit = int(data.get("critical", {}).get("bytes", 0))
        crit_max = int(data.get("budgets", {}).get("critical_max", 45000))
        if crit > crit_max:
            failures.append(f"critical bundle {crit}B > budget {crit_max}B")

    if failures:
        print("audit_marketing_prompt_complete: FAIL", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("audit_marketing_prompt_complete: OK — prompt 100% (repo-contained gates green)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
