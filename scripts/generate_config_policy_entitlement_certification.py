#!/usr/bin/env python3
"""Certification artifact for Stage 4 policy / entitlement / metadata / registries.

Writes:
  docs/generated/config_policy_entitlement_certification.json
  docs/generated/config_policy_entitlement_certification.md
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIT_JSON = ROOT / "docs" / "generated" / "policy_entitlement_runtime_audit.json"
CERT_JSON = ROOT / "docs" / "generated" / "config_policy_entitlement_certification.json"
CERT_MD = ROOT / "docs" / "generated" / "config_policy_entitlement_certification.md"

VERDICT_READY = "CONFIGURATION POLICY ENGINE READY — REPO SCOPE"
VERDICT_NOT_READY = "CONFIGURATION POLICY ENGINE NOT READY — REPO SCOPE"


def _bootstrap_django() -> None:
    sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _gate_checks(audit: dict) -> list[dict]:
    gates: list[dict] = []

    def add(gate_id: str, ok: bool, note: str) -> None:
        gates.append({"id": gate_id, "ok": ok, "note": note})

    central = audit.get("central_gate_modules") or {}
    for key, ok in sorted(central.items()):
        add(f"module_{key}", bool(ok), f"{key} present")

    health = audit.get("registry_health") or {}
    add(
        "registry_health_ok",
        bool(health.get("ok")),
        f"high={health.get('high_count', 0)} medium={health.get('medium_count', 0)}",
    )
    add("audit_ok", bool(audit.get("ok")), "discovery audit self-check")

    try:
        from apps.metadata.ddl_safety import contains_forbidden_ddl

        add(
            "metadata_ddl_guard",
            contains_forbidden_ddl("ALTER TABLE x") and not contains_forbidden_ddl("SELECT 1"),
            "DDL patterns blocked on metadata paths",
        )
    except Exception as exc:
        add("metadata_ddl_guard", False, str(exc))

    try:
        from apps.platform_runtime.entitlement_gates import invalidate_entitlement_cache

        invalidate_entitlement_cache(None)
        add("entitlement_cache_invalidate", True, "invalidate_entitlement_cache callable")
    except Exception as exc:
        add("entitlement_cache_invalidate", False, str(exc))

    return gates


def build_certification(audit: dict) -> dict:
    gates = _gate_checks(audit)
    failed = [g for g in gates if not g["ok"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": VERDICT_READY if not failed else VERDICT_NOT_READY,
        "repo_scope_only": True,
        "external_blockers": [
            "live_billing_psp_entitlement_sync",
            "counsel_signed_policy_pack_flip",
        ],
        "audit_ref": str(AUDIT_JSON.relative_to(ROOT)).replace("\\", "/"),
        "audit_generated_at": audit.get("generated_at"),
        "gates": gates,
        "failed_gate_count": len(failed),
        "focused_test_modules": audit.get("focused_test_modules", []),
        "sot_batch_draft": 1323,
    }


def _write_md(data: dict) -> str:
    lines = [
        "# Config policy entitlement certification",
        "",
        f"**Generated:** {data['generated_at']}",
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
    args = parser.parse_args()
    if not args.write:
        args.write = True

    if not AUDIT_JSON.is_file():
        subprocess.check_call(
            [
                sys.executable,
                str(ROOT / "scripts/generate_policy_entitlement_runtime_audit.py"),
                "--write",
            ],
            cwd=str(ROOT),
        )

    audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    _bootstrap_django()
    data = build_certification(audit)
    CERT_JSON.parent.mkdir(parents=True, exist_ok=True)
    CERT_JSON.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    CERT_MD.write_text(_write_md(data), encoding="utf-8")
    print(f"Wrote {CERT_JSON.relative_to(ROOT)}")
    print(f"Verdict: {data['verdict']}")
    return 1 if data["failed_gate_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
