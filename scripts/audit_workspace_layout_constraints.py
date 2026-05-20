#!/usr/bin/env python3
"""
Stage 8 workspace layout constraint audit — sticky+overflow traps, chromatic floor,
page-fold shell wiring for portal / dashboard / Studio OS / feedback surfaces.

Writes docs/generated/workspace_layout_constraint_audit.json
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "generated" / "workspace_layout_constraint_audit.json"

WORKSPACE_TABLE_SCAN_DIRS = (
    "templates/analytics/",
    "templates/feedback/",
    "templates/studio_os/",
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _run(script: str) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    tail = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, tail.strip()[-500:]


def main() -> int:
    checks: list[dict[str, object]] = []

    def record(cid: str, ok: bool, detail: str, proof: str = "") -> None:
        checks.append({"id": cid, "status": "PASS" if ok else "FAIL", "detail": detail, "proof": proof})

    sticky_code, sticky_tail = _run("scan_sticky_with_overflow_hidden.py")
    record(
        "sticky_overflow_hidden_baseline_zero",
        sticky_code == 0,
        "scan_sticky_with_overflow_hidden.py exit 0",
        sticky_tail,
    )

    fold_code, fold_tail = _run("verify_page_fold_standards.py")
    record(
        "page_fold_standards",
        fold_code == 0,
        "verify_page_fold_standards.py exit 0",
        fold_tail,
    )

    chromatic_code, chromatic_tail = _run("verify_platform_chromatic_compliance.py")
    record(
        "platform_chromatic_compliance",
        chromatic_code == 0,
        "verify_platform_chromatic_compliance.py exit 0",
        chromatic_tail,
    )

    luxury_code, luxury_tail = _run("audit_luxury_ui_surface.py")
    record(
        "luxury_ui_severe_integration",
        luxury_code == 0,
        "audit_luxury_ui_surface.py exit 0 (no shell inline / severe table violations)",
        luxury_tail,
    )

    studio_code, studio_tail = _run("verify_studio_workspace_layout.py")
    record(
        "studio_os_workspace_layout",
        studio_code == 0,
        "verify_studio_workspace_layout.py exit 0",
        studio_tail,
    )

    paginate_hits: list[str] = []
    for rel in WORKSPACE_TABLE_SCAN_DIRS:
        path = ROOT / rel
        if not path.is_dir():
            continue
        for f in sorted(path.rglob("*.html")):
            text = f.read_text(encoding="utf-8", errors="replace")
            if "<table" not in text.lower():
                continue
            if any(m in text for m in ("rmc-data-table", "table-family", "components/pagination.html")):
                continue
            if "data-rmc-scroll-policy=\"paginate\"" in text:
                continue
            paginate_hits.append(str(f.relative_to(ROOT)).replace("\\", "/"))

    record(
        "workspace_tables_paginate_or_family",
        len(paginate_hits) == 0,
        f"tables without .rmc-data-table or paginate policy: {len(paginate_hits)}",
        ", ".join(paginate_hits[:12]),
    )

    feedback_help = _read("templates/feedback/help_center.html")
    record(
        "feedback_help_center_loop",
        "You said" in feedback_help and "We did" in feedback_help,
        "help center ships You said / We did loop",
        "templates/feedback/help_center.html",
    )

    studio_shell = _read("templates/studio_os/shell.html")
    studio_style = _read("templates/studio_os/partials/shell_extrastyle.html")
    shells_ok = (
        "back_to_top.html" in _read("templates/portal_base.html")
        and "back_to_top.html" in _read("templates/control_plane_skeleton.html")
        and (
            "studio-workspace.css" in studio_shell
            or "shell_extrastyle.html" in studio_shell
            or "studio-workspace.css" in studio_style
        )
        and ("data-rmc-studio-workspace" in studio_shell or "workspace_layout.html" in studio_shell)
    )
    record("four_shell_workspace_assets", shells_ok, "portal/cp/studio shells wire fold + workspace CSS")

    failed = [c for c in checks if c["status"] == "FAIL"]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": 1,
        "verdict": "WORKSPACE_LAYOUT_READY" if not failed else "WORKSPACE_LAYOUT_GAPS",
        "checks": checks,
        "failure_count": len(failed),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} — {payload['verdict']} ({len(failed)} failures)")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
