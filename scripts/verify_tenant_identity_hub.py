#!/usr/bin/env python3
"""Verify tenant identity hub wiring and school-scoped RBAC guards."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "docs" / "generated" / "tenant_identity_hub_audit.json"


@dataclass
class Row:
    check_id: str
    ok: bool
    proof: str


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _run_tests() -> tuple[bool, str]:
    labels = [
        "apps.accounts.tests.test_tenant_identity",
        "apps.accounts.tests.test_tenant_rbac_scope",
        "apps.accounts.tests.test_iam_localization",
    ]
    import time

    env = {**os.environ, "RMC_SQLITE_TEST_MEMORY": "1"}
    last_tail = ""
    for flag in ("--keepdb", "--fresh"):
        if flag == "--fresh":
            tdir = ROOT / ".django_test_dbs"
            tdir.mkdir(parents=True, exist_ok=True)
            env["DJANGO_TEST_DB_FILE"] = str(
                tdir / f"tenant_identity_hub_{int(time.time())}.sqlite3"
            )
        cmd = [
            sys.executable,
            "scripts/run_sqlite_memory_tests.py",
            *labels,
            flag,
            "--verbosity=1",
        ]
        proc = subprocess.run(
            cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=900, env=env
        )
        last_tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-800:]
        if proc.returncode == 0:
            return True, last_tail
        if "database is locked" not in last_tail.lower():
            break
    return False, last_tail


def main() -> int:
    rows: list[Row] = []

    def add(check_id: str, ok: bool, proof: str) -> None:
        rows.append(Row(check_id, ok, proof))

    urls = _read("apps/accounts/urls.py")
    add("urls-roster", "tenant_identity_roster" in urls, "accounts/urls.py")
    add("urls-invite", "tenant_identity_invite" in urls, "accounts/urls.py")
    add("urls-accept", "tenant_staff_invite_accept" in urls, "accounts/urls.py")
    add(
        "urls-regulator",
        "tenant_identity_regulator_grant" in urls,
        "accounts/urls.py regulator",
    )
    add(
        "model-invite",
        "class TenantStaffInvite" in _read("apps/accounts/models.py"),
        "TenantStaffInvite model",
    )
    add(
        "helpers-module",
        (ROOT / "apps/accounts/tenant_identity.py").is_file(),
        "tenant_identity.py",
    )
    add(
        "views-module",
        (ROOT / "apps/accounts/views_tenant_identity.py").is_file(),
        "views_tenant_identity.py",
    )
    add(
        "template-roster",
        (ROOT / "templates/accounts/tenant_identity_roster.html").is_file(),
        "tenant_identity_roster.html",
    )
    add(
        "forms-school-scope",
        "users_queryset_for_school" in _read("apps/accounts/forms.py"),
        "forms school scope",
    )
    add(
        "rbac-membership-guard",
        "user_has_school_membership" in _read("apps/accounts/views.py"),
        "rbac membership guard",
    )
    add(
        "rbac-edit-role-school-scoped",
        "roles_queryset_for_school(school).prefetch_related"
        in _read("apps/accounts/views.py"),
        "rbac edit_role GET scoped",
    )
    add(
        "admin-tenant-scope",
        "TenantScopedUserAdmin" in _read("apps/accounts/admin.py"),
        "TenantScopedUserAdmin",
    )
    add(
        "admin-staff-invite",
        "TenantStaffInviteAdmin" in _read("apps/accounts/admin.py"),
        "TenantStaffInviteAdmin",
    )
    add(
        "api-staff-bypass-removed",
        "is_staff" not in _read("apps/schools/tenant_switch_security.py")
        or "user_is_platform_operator" in _read("apps/schools/tenant_switch_security.py"),
        "tenant_switch_security",
    )
    add(
        "nav-link",
        "tenant_identity" in _read("apps/siteconfig/portal_sidebar_items.py"),
        "portal sidebar",
    )
    add(
        "trust-hub-link",
        "tenant_identity" in _read("apps/accounts/views_trust_hub.py"),
        "trust hub urls",
    )
    roster = _read("templates/accounts/tenant_identity_roster.html")
    add(
        "roster-pagination",
        "components/pagination.html" in roster and 'data-rmc-scroll-policy="paginate"' in roster,
        "roster template",
    )
    add("roster-dead-hrefs", 'href="#"' not in roster, "no dead hrefs")
    add(
        "iam-localization-module",
        (ROOT / "apps/accounts/iam_localization.py").is_file(),
        "iam_localization.py",
    )
    views_src = _read("apps/accounts/views_tenant_identity.py")
    add(
        "regulator-grant-view",
        "tenant_identity_regulator_grant" in views_src
        and "TemporaryRoleGrant" in views_src,
        "regulator grant view",
    )
    add(
        "template-regulator",
        (ROOT / "templates/accounts/tenant_identity_regulator_grant.html").is_file(),
        "regulator template",
    )
    add(
        "localized-role-roster",
        "localized_role_for_user" in views_src,
        "localized roles in views",
    )

    migration = ROOT / "apps/accounts/migrations/0037_tenant_staff_invite.py"
    add("migration-0037", migration.is_file(), "0037 migration")

    tests_ok, tests_tail = _run_tests()
    add("django-tests", tests_ok, tests_tail or "tenant identity tests")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finding_count": sum(1 for r in rows if not r.ok),
        "rows": [{"check_id": r.check_id, "ok": r.ok, "proof": r.proof} for r in rows],
    }
    GENERATED.parent.mkdir(parents=True, exist_ok=True)
    GENERATED.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if payload["finding_count"]:
        print("TENANT_IDENTITY_HUB_FAIL")
        for r in rows:
            if not r.ok:
                print(f"  FAIL {r.check_id}: {r.proof[:200]}")
        return 1
    print("TENANT_IDENTITY_HUB_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
