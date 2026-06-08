#!/usr/bin/env python
"""Five-pass platform audit: tenant staff vs control-plane / manager-host RBAC.

Pass 1 — Operator identity helpers deny tenant-scoped staff via role alone.
Pass 2 — Public tenant auth paths stay on runmycampus.com (not manager redirect).
Pass 3 — Manager host bounces signup verify/resend flows to the public host.
Pass 4 — No duplicate operator-role allowlists bypassing membership guard.
Pass 5 — Access helpers agree for tenant ADMIN with SchoolMembership.

Usage:
  python scripts/verify_tenant_control_plane_rbac.py
  python scripts/verify_tenant_control_plane_rbac.py --strict
  python scripts/verify_tenant_control_plane_rbac.py --json
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = (
    REPO_ROOT / "var" / "security-audit-baseline-tenant-control-plane-rbac.json"
)

OPERATOR_IDENTITY = REPO_ROOT / "apps" / "platform_runtime" / "operator_identity.py"
CONTROL_PLANE = REPO_ROOT / "apps" / "schools" / "control_plane.py"
MIDDLEWARE = REPO_ROOT / "apps" / "schools" / "middleware.py"
MANAGER_URLS = REPO_ROOT / "config" / "manager_urls.py"
APPS_DIR = REPO_ROOT / "apps"

REQUIRED_PUBLIC_AUTH_PREFIXES = (
    "/authentication/login/",
    "/authentication/logout/",
    "/authentication/password_reset/",
    "/authentication/onboarding/",
    "/verify-signup/",
)

OPERATOR_ROLE_ENV_RE = re.compile(
    r"os\.environ\.get\s*\(\s*['\"]CONTROL_PLANE_OPERATOR_ROLES['\"]"
)
OPERATOR_ROLE_GETENV_RE = re.compile(
    r"os\.getenv\s*\(\s*['\"]CONTROL_PLANE_OPERATOR_ROLES['\"]"
)


def _finding(pass_id: str, reason: str, *, path: str = "") -> dict[str, str]:
    row: dict[str, str] = {"pass": pass_id, "reason": reason}
    if path:
        row["path"] = path
    return row


def pass1_operator_identity_membership_guard() -> list[dict[str, str]]:
    """operator_identity must block tenant membership before role-only operator grant."""
    findings: list[dict[str, str]] = []
    text = OPERATOR_IDENTITY.read_text(encoding="utf-8")

    if "user_is_tenant_scoped_staff" not in text:
        findings.append(
            _finding(
                "pass1",
                "operator_identity_missing_tenant_scoped_staff_import",
                path="apps/platform_runtime/operator_identity.py",
            )
        )

    if "def user_is_platform_operator" in text:
        fn_start = text.index("def user_is_platform_operator")
        fn_body = text[fn_start : fn_start + 2500]
        role_idx = fn_body.find("_operator_role_allowlist()")
        tenant_idx = fn_body.find("user_is_tenant_scoped_staff")
        if tenant_idx < 0 or (role_idx >= 0 and tenant_idx > role_idx):
            findings.append(
                _finding(
                    "pass1",
                    "user_is_platform_operator_must_deny_tenant_staff_before_role_check",
                    path="apps/platform_runtime/operator_identity.py",
                )
            )

    if "def user_effective_platform_scopes" in text:
        fn_start = text.index("def user_effective_platform_scopes")
        fn_body = text[fn_start : fn_start + 2500]
        role_idx = fn_body.find("_operator_role_allowlist()")
        tenant_idx = fn_body.find("user_is_tenant_scoped_staff")
        if tenant_idx < 0 or (role_idx >= 0 and tenant_idx > role_idx):
            findings.append(
                _finding(
                    "pass1",
                    "user_effective_platform_scopes_must_block_role_tier_for_tenant_staff",
                    path="apps/platform_runtime/operator_identity.py",
                )
            )

    if "_tenant_scoped_non_operator_user_ids" not in text:
        findings.append(
            _finding(
                "pass1",
                "queryset_platform_operators_missing_tenant_membership_exclude",
                path="apps/platform_runtime/operator_identity.py",
            )
        )

    cp_text = CONTROL_PLANE.read_text(encoding="utf-8")
    if "def user_is_tenant_scoped_staff" not in cp_text:
        findings.append(
            _finding(
                "pass1",
                "control_plane_missing_user_is_tenant_scoped_staff_export",
                path="apps/schools/control_plane.py",
            )
        )
    if "_user_has_tenant_membership(user)" not in cp_text.split(
        "def user_has_control_plane_access"
    )[1][:1200]:
        findings.append(
            _finding(
                "pass1",
                "user_has_control_plane_access_missing_tenant_membership_guard",
                path="apps/schools/control_plane.py",
            )
        )
    return findings


def pass2_public_tenant_auth_prefixes() -> list[dict[str, str]]:
    """PUBLIC_TENANT_AUTH_PREFIXES must cover all tenant-primary auth entry points."""
    findings: list[dict[str, str]] = []
    text = MIDDLEWARE.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return [
            _finding(
                "pass2",
                f"middleware_syntax_error:{exc}",
                path="apps/schools/middleware.py",
            )
        ]

    prefixes: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "PUBLIC_TENANT_AUTH_PREFIXES":
                if isinstance(node.value, (ast.Tuple, ast.List)):
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            prefixes.add(elt.value)

    for required in REQUIRED_PUBLIC_AUTH_PREFIXES:
        covered = any(
            required == p or required.startswith(p) or p.startswith(required.rstrip("/"))
            for p in prefixes
        )
        if not covered:
            findings.append(
                _finding(
                    "pass2",
                    f"missing_public_tenant_auth_prefix:{required}",
                    path="apps/schools/middleware.py",
                )
            )
    return findings


def _function_contains(path: Path, fn_name: str, needle: str) -> bool:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            segment = ast.get_source_segment(text, node) or ""
            return needle in segment
    return False


def pass3_manager_signup_public_redirect() -> list[dict[str, str]]:
    """Manager host must redirect signup verify/resend to public host."""
    findings: list[dict[str, str]] = []
    mw = MIDDLEWARE.read_text(encoding="utf-8")
    for needle in (
        'path.startswith("/verify-signup/")',
        "build_public_site_url",
    ):
        if needle not in mw:
            findings.append(
                _finding(
                    "pass3",
                    f"middleware_missing_manager_signup_redirect:{needle}",
                    path="apps/schools/middleware.py",
                )
            )

    mgr = MANAGER_URLS.read_text(encoding="utf-8")
    for needle in (
        "redirect_signup_flow_to_public",
        'path("verify-signup/"',
        '"verify-signup/resend/"',
    ):
        if needle not in mgr:
            findings.append(
                _finding(
                    "pass3",
                    f"manager_urls_missing_signup_public_parity:{needle}",
                    path="config/manager_urls.py",
                )
            )

    signup_views = REPO_ROOT / "apps" / "schools" / "signup_views.py"
    for fn_name in ("verify_signup", "resend_signup_verification"):
        if not _function_contains(signup_views, fn_name, "request_is_manager_host"):
            findings.append(
                _finding(
                    "pass3",
                    f"{fn_name}_missing_manager_host_public_redirect_guard",
                    path="apps/schools/signup_views.py",
                )
            )
    return findings


def pass4_no_duplicate_operator_role_env() -> list[dict[str, str]]:
    """CONTROL_PLANE_OPERATOR_ROLES must only be read in control_plane (single SOT)."""
    findings: list[dict[str, str]] = []
    allowed = {
        "apps/schools/control_plane.py",
    }
    for path in sorted(APPS_DIR.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        if rel in allowed:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if OPERATOR_ROLE_ENV_RE.search(text) or OPERATOR_ROLE_GETENV_RE.search(text):
            findings.append(
                _finding(
                    "pass4",
                    "duplicate_control_plane_operator_roles_env_read",
                    path=rel,
                )
            )
    return findings


def pass5_access_helper_parity() -> list[dict[str, str]]:
    """Runtime parity: tenant ADMIN owner denied by both access helpers."""
    findings: list[dict[str, str]] = []
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        import django

        django.setup()
    except Exception as exc:  # noqa: BLE001 — audit must report setup failure
        return [_finding("pass5", f"django_setup_failed:{exc}")]

    import uuid

    from django.contrib.auth import get_user_model

    from apps.platform_runtime.operator_identity import (
        user_effective_platform_scopes,
        user_is_platform_operator,
    )
    from apps.schools.control_plane import user_has_control_plane_access
    from apps.schools.models import School, SchoolMembership

    User = get_user_model()
    prev_env = os.environ.get("CONTROL_PLANE_OPERATOR_ROLES")
    os.environ["CONTROL_PLANE_OPERATOR_ROLES"] = "SUPERADMIN,ADMIN"
    school = None
    owner = None
    probe_slug = f"rbac-audit-probe-{uuid.uuid4().hex[:8]}"
    probe_username = f"rbac-audit-owner-{uuid.uuid4().hex[:8]}@test.local"
    try:
        school = School.objects.create(
            name="RBAC Audit Probe School",
            slug=probe_slug,
            subdomain=probe_slug,
            is_active=False,
        )
        owner = User.objects.create_user(
            username=probe_username,
            email=probe_username,
            password="unused",
            role=getattr(User, "Role", None).ADMIN if hasattr(User, "Role") else "ADMIN",
        )
        SchoolMembership.objects.create(
            user=owner,
            school=school,
            role=getattr(User, "Role", None).ADMIN if hasattr(User, "Role") else "ADMIN",
            is_primary=True,
        )

        if user_has_control_plane_access(owner):
            findings.append(
                _finding(
                    "pass5",
                    "tenant_owner_must_not_have_control_plane_access",
                )
            )
        if user_is_platform_operator(owner):
            findings.append(
                _finding(
                    "pass5",
                    "tenant_owner_must_not_be_platform_operator",
                )
            )
        principal_scopes = user_effective_platform_scopes(owner)
        if principal_scopes & {
            "platform.team.manage",
            "platform.provision.school",
            "platform.impersonate",
        }:
            findings.append(
                _finding(
                    "pass5",
                    "tenant_owner_must_not_inherit_principal_platform_scopes",
                )
            )
    finally:
        if prev_env is None:
            os.environ.pop("CONTROL_PLANE_OPERATOR_ROLES", None)
        else:
            os.environ["CONTROL_PLANE_OPERATOR_ROLES"] = prev_env
        try:
            if school is not None:
                SchoolMembership.objects.filter(school=school).delete()
                school.delete()
            if owner is not None:
                owner.delete()
        except Exception:  # noqa: BLE001 — best-effort probe cleanup
            pass
    return findings


def run_all_passes() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    findings.extend(pass1_operator_identity_membership_guard())
    findings.extend(pass2_public_tenant_auth_prefixes())
    findings.extend(pass3_manager_signup_public_redirect())
    findings.extend(pass4_no_duplicate_operator_role_env())
    findings.extend(pass5_access_helper_parity())
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Exit 1 when findings > 0")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args(argv)

    findings = run_all_passes()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finding_count": len(findings),
        "passes": 5,
        "findings": findings,
    }

    if args.write_baseline:
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote baseline: {BASELINE_PATH} ({len(findings)} findings)")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        if findings:
            print(f"TENANT_CONTROL_PLANE_RBAC_FAIL: {len(findings)} finding(s)")
            for row in findings:
                loc = row.get("path", "")
                prefix = f"  [{row['pass']}]"
                if loc:
                    print(f"{prefix} {loc}: {row['reason']}")
                else:
                    print(f"{prefix} {row['reason']}")
        else:
            print("TENANT_CONTROL_PLANE_RBAC_PASS")

    if args.strict and findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
