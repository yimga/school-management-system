#!/usr/bin/env python3
"""Static completeness audit for batch 1505 (scopes + AccessRole school catalog)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "batch_1505_completeness_audit.json"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    rows: list[dict] = []

    def add(check_id: str, ok: bool, proof: str) -> None:
        rows.append({"check_id": check_id, "ok": ok, "proof": proof})

    views = _read("apps/accounts/views.py")
    add(
        "rbac-edit-role-get-scoped",
        "roles_queryset_for_school(school).prefetch_related" in views
        and "AccessRole.objects.prefetch_related" not in views.split("edit_role")[1][:800]
        if "edit_role" in views
        else False,
        "edit_role GET uses school queryset",
    )
    add(
        "rbac-temp-grants-school-filter",
        "school_user_ids = users_queryset_for_school(school)" in views,
        "temporary grants filtered to school",
    )
    add(
        "migration-0038",
        (ROOT / "apps/accounts/migrations/0038_accessrole_school_scope.py").is_file(),
        "0038 migration present",
    )
    add(
        "regulator-role-school",
        'school=school,\n        code="regulatory_auditor"' in _read(
            "apps/accounts/views_tenant_identity.py"
        ),
        "regulator grant uses school FK",
    )

    for script, token in (
        ("verify_super_platform_scope_coverage.py", "SUPER_PLATFORM_SCOPE_COVERAGE_PASS"),
    ):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        add(script, token in (proc.stdout or ""), token if proc.returncode == 0 else proc.stderr[-200:])

    # Honest gaps (documented, not failures)
    deferred = [
        "Zanzibar/ReBAC graph engine — NOT_IMPLEMENTED (manifest documents)",
        "CRDT edge IAM — NOT_IMPLEMENTED (manifest documents)",
        "operator_invite_accept — public by design (token URL)",
        "super_config_hub_redirect — redirect only",
    ]

    finding_count = sum(1 for r in rows if not r["ok"])
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finding_count": finding_count,
        "rows": rows,
        "honest_deferred": deferred,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if finding_count:
        print("BATCH_1505_COMPLETENESS_FAIL")
        for r in rows:
            if not r["ok"]:
                print(f"  {r['check_id']}: {r['proof']}")
        return 1
    print("BATCH_1505_COMPLETENESS_PASS")
    print(f"  deferred_items={len(deferred)} (documented, not gated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
