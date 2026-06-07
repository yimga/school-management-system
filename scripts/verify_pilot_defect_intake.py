#!/usr/bin/env python3
"""Batch 1175 — repo-scope pilot defect intake scaffold verifier."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    findings: list[str] = []

    urls_py = ROOT / "apps/platform_runtime/urls.py"
    if not urls_py.is_file() or "pilot_defect_dashboard" not in urls_py.read_text(encoding="utf-8"):
        findings.append("pilot_defect_dashboard route missing from apps/platform_runtime/urls.py")

    dash_tpl = ROOT / "templates/platform_runtime/pilot_defect_dashboard.html"
    if not dash_tpl.is_file() or "File pilot feedback" not in dash_tpl.read_text(encoding="utf-8"):
        findings.append("pilot_defect_dashboard missing intake form")

    export_cmd = ROOT / "apps/platform_runtime/management/commands/export_pilot_defect_backlog.py"
    if not export_cmd.is_file():
        findings.append("missing export_pilot_defect_backlog management command")

    model_path = ROOT / "apps/platform_runtime/models.py"
    if not model_path.is_file() or "class PilotDefect" not in model_path.read_text(encoding="utf-8"):
        findings.append("PilotDefect model missing")

    backlog = ROOT / "var/evidence/geos-99/pilot/gilead-school/defect_backlog.json"
    if not backlog.is_file():
        findings.append("missing defect_backlog.json")
    else:
        data = json.loads(backlog.read_text(encoding="utf-8"))
        if data.get("schema_version") != 1:
            findings.append("defect_backlog schema_version != 1")

    scorecard = ROOT / "docs/generated/pilot_readiness_scorecard.json"
    if not scorecard.is_file():
        findings.append("missing pilot_readiness_scorecard.json")
    else:
        sc = json.loads(scorecard.read_text(encoding="utf-8"))
        pilots = sc.get("pilots") or []
        if len(pilots) < 2:
            findings.append("scorecard needs slot 2 for external pilot")
        elif pilots[1].get("onboarding_status") == "not_started":
            pass  # expected until real school

    intake = sorted((ROOT / "var/evidence/geos-99/pilot/gilead-school").glob("intake_ready_*.json"))
    if not intake:
        findings.append("missing intake_ready_*.json evidence")

    if findings:
        print("verify_pilot_defect_intake: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_pilot_defect_intake: PILOT_DEFECT_INTAKE_SCAFFOLD_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
