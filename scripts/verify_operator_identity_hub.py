#!/usr/bin/env python3
"""Verify platform operator identity hub (/super/team/) wiring."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "docs" / "generated" / "operator_identity_hub_audit.json"


@dataclass
class Row:
    check_id: str
    ok: bool
    proof: str


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _run_tests() -> tuple[bool, str]:
    cmd = [
        sys.executable,
        "scripts/run_sqlite_memory_tests.py",
        "apps.platform_runtime.tests.test_operator_identity",
        "--verbosity=1",
        "--no-input",
    ]
    env = {**os.environ, "RMC_SQLITE_TEST_MEMORY": "1"}
    proc = subprocess.run(
        cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=600, env=env
    )
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip()[-800:]
    return proc.returncode == 0, tail


def main() -> int:
    rows: list[Row] = []

    def add(check_id: str, ok: bool, proof: str) -> None:
        rows.append(Row(check_id, ok, proof))

    urls = _read("apps/schools/super_urls.py")
    add("super-urls-team-roster", "operator_team_roster" in urls, "super_urls.py")
    add("super-urls-team-invite", "operator_team_invite" in urls, "super_urls.py")
    add(
        "accounts-url-invite-accept",
        "operator_invite_accept" in _read("apps/accounts/urls.py"),
        "accounts/urls.py",
    )
    add(
        "model-profile",
        (ROOT / "apps/platform_runtime/models_operator_identity.py").is_file(),
        "models_operator_identity.py",
    )
    add(
        "middleware-mfa",
        (ROOT / "apps/schools/middleware_operator_mfa.py").is_file(),
        "middleware_operator_mfa.py",
    )
    add(
        "template-roster",
        (ROOT / "templates/schools/super_operator_team_roster.html").is_file(),
        "super_operator_team_roster.html",
    )
    add(
        "template-detail",
        (ROOT / "templates/schools/super_operator_team_detail.html").is_file(),
        "super_operator_team_detail.html",
    )
    add(
        "nav-link",
        "super:operator_team_roster" in _read("apps/schools/control_plane_nav.py"),
        "control_plane_nav.py",
    )
    add(
        "platform-user-admin",
        "PlatformUserAdmin" in _read("apps/accounts/admin.py"),
        "accounts/admin.py",
    )
    add(
        "feedback-is-operator",
        "user_is_platform_operator" in _read("apps/feedback/services.py"),
        "feedback/services.py",
    )

    roster = _read("templates/schools/super_operator_team_roster.html")
    add(
        "roster-pagination",
        "components/pagination.html" in roster and 'data-rmc-scroll-policy="paginate"' in roster,
        "roster template",
    )
    add(
        "roster-dead-hrefs",
        'href="#"' not in roster,
        "no dead hrefs in roster",
    )
    invite = _read("templates/schools/super_operator_team_invite.html")
    add(
        "invite-operational-frame",
        "rmc_operational_center_frame.html" in invite,
        "invite template frame",
    )
    add(
        "canonical-admin-guard",
        "user_may_offboard_operator" in _read("apps/schools/super_views_operator_team.py")
        and "CANONICAL_PLATFORM_ADMIN_USERNAME" in _read("apps/platform_runtime/operator_identity.py"),
        "canonical admin protection",
    )
    add(
        "migration-0075-admin-profile",
        (ROOT / "apps/platform_runtime/migrations/0075_ensure_admin_operator_profile.py").is_file(),
        "0075 migration",
    )
    mfa_src = _read("apps/schools/middleware_operator_mfa.py")
    add(
        "operator-mfa-session-verify",
        "RequireMFAMiddleware._is_mfa_verified" in mfa_src,
        "operator MFA session verify",
    )
    add(
        "impersonation-scope",
        "PLATFORM_SCOPE_IMPERSONATE" in _read("apps/schools/super_views_impersonation.py"),
        "impersonation scope",
    )
    add(
        "provision-scope",
        "PLATFORM_SCOPE_PROVISION" in _read("apps/schools/super_views_provisioning.py"),
        "provision scope",
    )
    add(
        "break-glass-admin",
        "PLATFORM_SCOPE_BREAK_GLASS_ADMIN" in _read("config/admin.py"),
        "break glass admin gate",
    )
    invite_accept = _read("apps/schools/super_views_operator_team.py")
    add(
        "invite-no-superuser",
        "user.is_superuser = False" in invite_accept,
        "invite accept no superuser",
    )
    add(
        "promotion-peer-only",
        "promo.peer_approver_id == request.user.pk" in invite_accept
        and "request.user.is_superuser\n                or promo.peer_approver_id" not in invite_accept,
        "promotion peer-only UI",
    )
    add(
        "operator-suspend-reactivate",
        "super_operator_team_suspend" in urls and "super_operator_team_reactivate" in urls,
        "suspend/reactivate URLs",
    )
    add(
        "billing-scope-gate",
        "PLATFORM_SCOPE_BILLING_READ" in _read("apps/schools/super_views_billing_console.py"),
        "billing scope",
    )
    add(
        "audit-export-scope-gate",
        "PLATFORM_SCOPE_AUDIT_EXPORT" in _read("apps/schools/super_views_trust_surface.py"),
        "audit export scope",
    )
    add(
        "migration-manage-scope",
        "PLATFORM_SCOPE_MIGRATION" in _read("apps/schools/super_views_migration.py"),
        "migration cloud scope",
    )
    add(
        "tenant-read-scope-monitoring",
        "PLATFORM_SCOPE_TENANT_READ"
        in _read("apps/schools/super_views_platform_monitoring.py"),
        "tenant monitoring scope",
    )
    add(
        "accessrole-school-migration",
        (ROOT / "apps/accounts/migrations/0038_accessrole_school_scope.py").is_file(),
        "0038_accessrole_school_scope",
    )

    tests_ok, tests_tail = _run_tests()
    add("django-tests", tests_ok, tests_tail or "test_operator_identity")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finding_count": sum(1 for r in rows if not r.ok),
        "rows": [{"check_id": r.check_id, "ok": r.ok, "proof": r.proof} for r in rows],
    }
    GENERATED.parent.mkdir(parents=True, exist_ok=True)
    GENERATED.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if payload["finding_count"]:
        print("OPERATOR_IDENTITY_HUB_FAIL")
        for r in rows:
            if not r.ok:
                print(f"  FAIL {r.check_id}: {r.proof[:200]}")
        return 1
    print("OPERATOR_IDENTITY_HUB_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
