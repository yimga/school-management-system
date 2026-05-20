#!/usr/bin/env python3
"""Academic operations certification from workflow audit + in-repo gates.

Writes:
  docs/generated/academic_operations_certification.json
  docs/generated/academic_operations_certification.md
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIT_JSON = ROOT / "docs" / "generated" / "academic_operations_workflow_audit.json"
CERT_JSON = ROOT / "docs" / "generated" / "academic_operations_certification.json"
CERT_MD = ROOT / "docs" / "generated" / "academic_operations_certification.md"

SOT_VERDICT = "ACADEMIC OPERATIONS READY — REPO SCOPE"
SOT_BATCH_DRAFT = 1325


def _run(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _gate_checks(audit: dict) -> list[dict]:
    gates: list[dict] = []

    def add(gate_id: str, ok: bool, note: str) -> None:
        gates.append({"id": gate_id, "ok": ok, "note": note})

    add("workflow_audit_ok", bool(audit.get("ok")), "academic_operations_workflow_audit.json ok")
    add(
        "no_unsafe_grade_json_blobs",
        not audit.get("unsafe_grade_json_blob_findings"),
        "relational grades preserved (no compressed JSON blob models)",
    )
    wl = audit.get("workflow_loop") or {}
    add(
        "offline_action_conflict_loop",
        bool(wl.get("offline_action_conflict_in_catalog"))
        and bool(wl.get("domain_event_bridge_maps_conflict"))
        and bool(wl.get("offline_queue_emits_conflict_event")),
        "offline_action_conflict → platform event → workflow bridge",
    )
    emis = audit.get("emis") or {}
    add("emis_export_compiler", all(emis.values()), "EMIS service + mapping + tests")

    code, _ = _run(
        [
            sys.executable,
            str(ROOT / "scripts/run_sqlite_memory_tests.py"),
            "apps.academics.tests.test_academic_operations_repo_scope",
            "--verbosity=1",
        ],
    )
    add(
        "stage6_repo_scope_contract_tests",
        code == 0,
        "test_academic_operations_repo_scope (EMIS relational export, P4 bridge, student360, publish route)",
    )

    return gates


def build_certification(audit: dict) -> dict:
    gates = _gate_checks(audit)
    failed = [g for g in gates if not g["ok"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sot_batch_draft": SOT_BATCH_DRAFT,
        "verdict": SOT_VERDICT if not failed else "ACADEMIC OPERATIONS NOT READY — REPO SCOPE",
        "repo_scope_only": True,
        "external_blockers": [
            "live_ministry_emis_submission_endpoint",
            "production_sms_provider_delivery_proof",
            "national_exam_board_api_integrations",
        ],
        "audit_ref": str(AUDIT_JSON.relative_to(ROOT)).replace("\\", "/"),
        "audit_generated_at": audit.get("generated_at"),
        "gates": gates,
        "failed_gate_count": len(failed),
        "focused_test_modules": audit.get("focused_test_modules", []),
    }


def _write_md(data: dict) -> str:
    lines = [
        "# Academic operations certification",
        "",
        f"**Generated:** {data['generated_at']}",
        f"**SOT batch draft:** {data['sot_batch_draft']}",
        f"**Verdict:** {data['verdict']}",
        "",
        f"Audit: `{data['audit_ref']}`",
        "",
        "## Gates",
        "",
        "| Gate | OK | Note |",
        "|------|----|------|",
    ]
    for g in data["gates"]:
        lines.append(f"| {g['id']} | {g['ok']} | {g['note']} |")
    lines.extend(["", "## External (not repo-proven)", ""])
    for item in data["external_blockers"]:
        lines.append(f"- {item}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--skip-tests", action="store_true", help="Skip embedded test gate (CI split)")
    args = parser.parse_args()
    if not args.write:
        args.write = True

    if not AUDIT_JSON.is_file():
        subprocess.check_call(
            [
                sys.executable,
                str(ROOT / "scripts/generate_academic_operations_workflow_audit.py"),
                "--write",
            ],
            cwd=str(ROOT),
        )

    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    data = build_certification(audit)
    if args.skip_tests:
        data["gates"] = [
            g
            for g in data["gates"]
            if g["id"] != "stage6_repo_scope_contract_tests"
        ]
        failed = [g for g in data["gates"] if not g["ok"]]
        data["failed_gate_count"] = len(failed)
        data["verdict"] = SOT_VERDICT if not failed else data["verdict"]

    CERT_JSON.parent.mkdir(parents=True, exist_ok=True)
    CERT_JSON.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    CERT_MD.write_text(_write_md(data), encoding="utf-8")
    print(f"Wrote {CERT_JSON.relative_to(ROOT)}")
    print(f"Verdict: {data['verdict']}")
    return 1 if data["failed_gate_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
