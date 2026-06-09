#!/usr/bin/env python
"""Eight-pass signup → provision → portal-ready production audit.

Pass 1 — Provisioning activates school + signup_completion_notifications wired.
Pass 2 — Portal-ready email payload includes tenant_portal_url + account_ready.
Pass 3 — Active tenant subdomain resolves in middleware (not school-not-found).
Pass 4 — Tenant-host membership guard blocks cross-tenant authenticated access.
Pass 5 — Runtime integration: inactive→active + notification idempotency.
Pass 6 — In-app inbox + SMS + web push portal-ready channels wired.
Pass 7 — First-visit corner toast + web-push nudge after subscribe.
Pass 8 — Welcome email uses public onboarding URL + HTML alternative (not raw subdomain).
Pass 9 — Platform recovery CLI ``activate_pending_signup_schools`` (--all-verified-inactive).

Usage:
  python scripts/verify_signup_production_readiness.py --strict
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / "var" / "security-audit-baseline-signup-production-readiness.json"

TASKS = REPO_ROOT / "apps" / "schools" / "tasks.py"
NOTIFY = REPO_ROOT / "apps" / "schools" / "signup_completion_notifications.py"
CHANNELS = REPO_ROOT / "apps" / "schools" / "signup_portal_channel_notifications.py"
CORNER = REPO_ROOT / "apps" / "schools" / "portal_ready_corner_notifications.py"
MIDDLEWARE = REPO_ROOT / "apps" / "schools" / "middleware.py"
EMAIL_HTML = REPO_ROOT / "templates" / "emails" / "tenant_admin_signup_completed.html"
ONBOARDING = REPO_ROOT / "apps" / "accounts" / "views_owner_onboarding.py"


def _finding(pass_id: str, reason: str, *, path: str = "") -> dict[str, str]:
    row = {"pass": pass_id, "reason": reason}
    if path:
        row["path"] = path
    return row


def pass1_provision_activation_hook() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    tasks = TASKS.read_text(encoding="utf-8")
    if "finalize_tenant_activation" not in tasks:
        findings.append(
            _finding(
                "pass1",
                "tasks_missing_finalize_tenant_activation",
                path="apps/schools/tasks.py",
            )
        )
    if "school.is_active = True" not in tasks:
        findings.append(
            _finding("pass1", "tasks_missing_is_active_flip", path="apps/schools/tasks.py")
        )
    if not NOTIFY.is_file():
        findings.append(
            _finding(
                "pass1",
                "signup_completion_notifications_module_missing",
                path="apps/schools/signup_completion_notifications.py",
            )
        )
    onboarding = ONBOARDING.read_text(encoding="utf-8")
    if "_run_owner_provisioning" not in onboarding.split("def form_valid")[1][:600]:
        findings.append(
            _finding(
                "pass1",
                "owner_onboarding_account_step_must_kick_provisioning",
                path="apps/accounts/views_owner_onboarding.py",
            )
        )
    return findings


def pass2_portal_ready_email_contract() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    notify = NOTIFY.read_text(encoding="utf-8")
    for needle in (
        "tenant_portal_url",
        "account_ready",
        "notify_tenant_signup_completed",
        "tenant.signup.completed",
    ):
        if needle not in notify:
            findings.append(
                _finding(
                    "pass2",
                    f"signup_completion_missing:{needle}",
                    path="apps/schools/signup_completion_notifications.py",
                )
            )
    html = EMAIL_HTML.read_text(encoding="utf-8")
    for needle in ("tenant_portal_url", "account_ready"):
        if needle not in html:
            findings.append(
                _finding(
                    "pass2",
                    f"email_template_missing:{needle}",
                    path="templates/emails/tenant_admin_signup_completed.html",
                )
            )
    return findings


def pass3_active_subdomain_resolution() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    mw = MIDDLEWARE.read_text(encoding="utf-8")
    if "is_active=True" not in mw:
        findings.append(
            _finding(
                "pass3",
                "middleware_must_filter_active_schools_for_subdomain",
                path="apps/schools/middleware.py",
            )
        )
    pending = (REPO_ROOT / "apps" / "schools" / "pending_tenant_discovery.py").read_text(
        encoding="utf-8"
    )
    if "school_subdomain_redirect_is_safe" not in pending:
        findings.append(
            _finding(
                "pass3",
                "pending_discovery_must_use_tenant_url_when_active",
                path="apps/schools/pending_tenant_discovery.py",
            )
        )
    return findings


def pass4_tenant_membership_guard() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    mw = MIDDLEWARE.read_text(encoding="utf-8")
    settings_txt = (REPO_ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    if "_enforce_tenant_host_membership" not in mw:
        findings.append(
            _finding(
                "pass4",
                "middleware_missing_tenant_host_membership_guard",
                path="apps/schools/middleware.py",
            )
        )
    else:
        try:
            tree = ast.parse(mw)
        except SyntaxError as exc:
            return [
                _finding("pass4", f"middleware_syntax_error:{exc}", path="apps/schools/middleware.py")
            ]
        fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "_enforce_tenant_host_membership":
                fn = ast.get_source_segment(mw, node) or ""
                break
        if not fn or "SchoolMembership" not in fn:
            findings.append(
                _finding(
                    "pass4",
                    "membership_guard_must_query_SchoolMembership",
                    path="apps/schools/middleware.py",
                )
            )
    if "class TenantHostMembershipMiddleware" not in mw:
        findings.append(
            _finding(
                "pass4",
                "middleware_missing_TenantHostMembershipMiddleware_class",
                path="apps/schools/middleware.py",
            )
        )
    if "TenantHostMembershipMiddleware" not in settings_txt:
        findings.append(
            _finding(
                "pass4",
                "settings_must_wire_TenantHostMembershipMiddleware_after_auth",
                path="config/settings.py",
            )
        )
    login = (REPO_ROOT / "apps" / "accounts" / "views.py").read_text(encoding="utf-8")
    if "resolve_post_login_tenant_membership" not in login:
        findings.append(
            _finding(
                "pass4",
                "login_must_use_resolve_post_login_tenant_membership",
                path="apps/accounts/views.py",
            )
        )
    return findings


def pass5_runtime_integration() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        import django

        django.setup()
    except Exception as exc:  # noqa: BLE001
        return [_finding("pass5", f"django_setup_failed:{exc}")]

    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from apps.schools.models import School, SchoolMembership, SignupVerification
    from apps.schools.signup_completion_notifications import (
        build_signup_completed_payload,
        notify_tenant_signup_completed,
    )
    from apps.schools.tasks import complete_provisioning_for_school

    User = get_user_model()
    slug = f"signup-audit-{timezone.now().strftime('%H%M%S')}"
    school = School.objects.create(
        name="Signup Audit School",
        slug=slug,
        subdomain=slug,
        is_active=False,
    )
    owner = User.objects.create_user(
        username=f"owner-{slug}@audit.test",
        email=f"owner-{slug}@audit.test",
        password="AuditPass123!",
        role=getattr(User, "Role", None).ADMIN if hasattr(User, "Role") else "ADMIN",
    )
    SchoolMembership.objects.create(
        user=owner, school=school, role=User.Role.ADMIN, is_primary=True
    )
    SignupVerification.objects.create(
        school=school,
        email=owner.email,
        expires_at=timezone.now() + timezone.timedelta(days=2),
        verified_at=timezone.now(),
    )
    try:
        result = complete_provisioning_for_school(str(school.pk), contact_email=owner.email)
        school.refresh_from_db(fields=["is_active", "settings"])
        if not result.get("is_active") and not school.is_active:
            findings.append(_finding("pass5", "complete_provisioning_did_not_activate_school"))
        payload = build_signup_completed_payload(school, owner.email, admin_user=owner)
        if not payload.get("tenant_portal_url"):
            findings.append(_finding("pass5", "payload_missing_tenant_portal_url"))
        if not payload.get("account_ready"):
            findings.append(_finding("pass5", "payload_account_ready_false_after_password"))
        if slug not in (payload.get("tenant_portal_url") or ""):
            findings.append(_finding("pass5", "tenant_portal_url_missing_subdomain"))
        if school.is_active:
            notify_tenant_signup_completed(school, owner.email, admin_user=owner)
            school.refresh_from_db(fields=["settings"])
            if not ((school.settings or {}).get("signup_notifications") or {}).get(
                "completed_dispatched_at"
            ) and not ((school.settings or {}).get("signup_notifications") or {}).get(
                "completed_at"
            ):
                findings.append(_finding("pass5", "notification_not_marked_completed"))
    finally:
        try:
            SchoolMembership.objects.filter(school=school).delete()
            SignupVerification.objects.filter(school=school).delete()
            school.delete()
            owner.delete()
        except Exception:  # noqa: BLE001
            pass
    return findings


def pass6_portal_ready_channels() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not CHANNELS.is_file():
        findings.append(
            _finding(
                "pass6",
                "signup_portal_channel_notifications_module_missing",
                path="apps/schools/signup_portal_channel_notifications.py",
            )
        )
        return findings
    channels = CHANNELS.read_text(encoding="utf-8")
    notify = NOTIFY.read_text(encoding="utf-8")
    for needle in (
        "ensure_portal_ready_in_app_notification",
        "notify_portal_ready_sms",
        "notify_portal_ready_web_push",
        "dispatch_portal_ready_channels",
        "Notification",
        "send_sms",
    ):
        if needle not in channels:
            findings.append(
                _finding(
                    "pass6",
                    f"portal_channels_missing:{needle}",
                    path="apps/schools/signup_portal_channel_notifications.py",
                )
            )
    if "dispatch_portal_ready_channels" not in notify:
        findings.append(
            _finding(
                "pass6",
                "signup_completion_must_dispatch_portal_ready_channels",
                path="apps/schools/signup_completion_notifications.py",
            )
        )
    web_push = REPO_ROOT / "apps" / "communication" / "web_push_service.py"
    if not web_push.is_file():
        findings.append(
            _finding(
                "pass6",
                "web_push_service_module_missing",
                path="apps/communication/web_push_service.py",
            )
        )
    else:
        wp_txt = web_push.read_text(encoding="utf-8")
        for needle in ("send_web_push_to_user", "vapid_configured", "WebPushSubscription"):
            if needle not in wp_txt:
                findings.append(
                    _finding(
                        "pass6",
                        f"web_push_service_missing:{needle}",
                        path="apps/communication/web_push_service.py",
                    )
                )
    sw = REPO_ROOT / "static" / "js" / "service-worker.js"
    if sw.is_file():
        sw_txt = sw.read_text(encoding="utf-8")
        if 'addEventListener("push"' not in sw_txt:
            findings.append(
                _finding(
                    "pass6",
                    "service_worker_missing_push_handler",
                    path="static/js/service-worker.js",
                )
            )
    e2e = REPO_ROOT / "tests" / "e2e" / "signup-production-smoke.spec.js"
    if not e2e.is_file():
        findings.append(
            _finding(
                "pass6",
                "signup_production_smoke_e2e_missing",
                path="tests/e2e/signup-production-smoke.spec.js",
            )
        )
    return findings


def pass7_first_visit_corner_and_nudge() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not CORNER.is_file():
        findings.append(
            _finding(
                "pass7",
                "portal_ready_corner_notifications_module_missing",
                path="apps/schools/portal_ready_corner_notifications.py",
            )
        )
        return findings
    corner = CORNER.read_text(encoding="utf-8")
    for needle in (
        "portal_ready_corner_for_request",
        "mark_portal_ready_corner_dismissed",
        "nudge_portal_ready_web_push",
        "PORTAL_READY_INBOX_TITLE",
        "browser_notify",
    ):
        if needle not in corner:
            findings.append(
                _finding(
                    "pass7",
                    f"portal_corner_missing:{needle}",
                    path="apps/schools/portal_ready_corner_notifications.py",
                )
            )

    ctx = (REPO_ROOT / "apps" / "accounts" / "context_processors_security.py").read_text(
        encoding="utf-8"
    )
    if "portal_ready_corner_for_request" not in ctx:
        findings.append(
            _finding(
                "pass7",
                "context_processor_must_merge_portal_ready_corner",
                path="apps/accounts/context_processors_security.py",
            )
        )

    security_views = (REPO_ROOT / "apps" / "accounts" / "views_security.py").read_text(
        encoding="utf-8"
    )
    if "mark_portal_ready_corner_dismissed" not in security_views:
        findings.append(
            _finding(
                "pass7",
                "corner_dismiss_must_wire_in_views_security",
                path="apps/accounts/views_security.py",
            )
        )

    urls = (REPO_ROOT / "apps" / "accounts" / "urls.py").read_text(encoding="utf-8")
    if "web_push_nudge_portal_ready" not in urls:
        findings.append(
            _finding(
                "pass7",
                "web_push_nudge_route_missing",
                path="apps/accounts/urls.py",
            )
        )

    portal_base = REPO_ROOT / "templates" / "portal_base.html"
    if portal_base.is_file():
        pb = portal_base.read_text(encoding="utf-8")
        if "rmc_web_push_boot.html" not in pb:
            findings.append(
                _finding(
                    "pass7",
                    "portal_base_missing_web_push_boot",
                    path="templates/portal_base.html",
                )
            )
    else:
        findings.append(
            _finding("pass7", "portal_base_missing", path="templates/portal_base.html")
        )

    corner_js = REPO_ROOT / "static" / "js" / "rmc-notification-corner.js"
    if corner_js.is_file():
        js = corner_js.read_text(encoding="utf-8")
        if "browser_notify" not in js:
            findings.append(
                _finding(
                    "pass7",
                    "notification_corner_missing_browser_notify",
                    path="static/js/rmc-notification-corner.js",
                )
            )
    else:
        findings.append(
            _finding(
                "pass7",
                "notification_corner_js_missing",
                path="static/js/rmc-notification-corner.js",
            )
        )

    notify = NOTIFY.read_text(encoding="utf-8")
    for channel_key in (
        "in_app_dispatched_at",
        "sms_dispatched_at",
        "web_push_dispatched_at",
    ):
        if channel_key not in notify:
            findings.append(
                _finding(
                    "pass7",
                    f"force_resend_must_clear:{channel_key}",
                    path="apps/schools/signup_completion_notifications.py",
                )
            )
    return findings


def pass8_welcome_email_public_host_contract() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    welcome = REPO_ROOT / "apps" / "schools" / "welcome_email.py"
    urls = REPO_ROOT / "apps" / "schools" / "provision_email_urls.py"
    if not welcome.is_file():
        findings.append(
            _finding(
                "pass8",
                "welcome_email_module_missing",
                path="apps/schools/welcome_email.py",
            )
        )
        return findings
    welcome_txt = welcome.read_text(encoding="utf-8")
    urls_txt = urls.read_text(encoding="utf-8") if urls.is_file() else ""
    for needle in (
        "build_owner_onboarding_url",
        "html_body=html",
        "send_transactional",
        "build_public_login_url",
    ):
        if needle not in welcome_txt:
            findings.append(
                _finding(
                    "pass8",
                    f"welcome_email_missing:{needle}",
                    path="apps/schools/welcome_email.py",
                )
            )
    for needle in (
        "build_owner_onboarding_url",
        "school_subdomain_redirect_is_safe",
        "build_public_login_url",
    ):
        if needle not in urls_txt:
            findings.append(
                _finding(
                    "pass8",
                    f"provision_email_urls_missing:{needle}",
                    path="apps/schools/provision_email_urls.py",
                )
            )
    return findings


def pass9_platform_recovery_cli() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    cmd = (
        REPO_ROOT
        / "apps"
        / "schools"
        / "management"
        / "commands"
        / "activate_pending_signup_schools.py"
    )
    if not cmd.is_file():
        findings.append(
            _finding(
                "pass9",
                "activate_pending_signup_schools_command_missing",
                path="apps/schools/management/commands/activate_pending_signup_schools.py",
            )
        )
        return findings
    txt = cmd.read_text(encoding="utf-8")
    for needle in (
        "--all-verified-inactive",
        "complete_provisioning_for_school",
        "verified_at__isnull=False",
        "--dry-run",
    ):
        if needle not in txt:
            findings.append(
                _finding(
                    "pass9",
                    f"recovery_cli_missing:{needle}",
                    path="apps/schools/management/commands/activate_pending_signup_schools.py",
                )
            )
    checklist = (
        REPO_ROOT / "docs" / "deployment" / "PRODUCTION_DEPLOYMENT_CHECKLIST.md"
    )
    if checklist.is_file():
        doc = checklist.read_text(encoding="utf-8")
        if "activate_pending_signup_schools" not in doc:
            findings.append(
                _finding(
                    "pass9",
                    "deploy_checklist_must_document_activate_pending_signup_schools",
                    path="docs/deployment/PRODUCTION_DEPLOYMENT_CHECKLIST.md",
                )
            )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--write-baseline", action="store_true")
    args = parser.parse_args(argv)

    findings: list[dict[str, str]] = []
    findings.extend(pass1_provision_activation_hook())
    findings.extend(pass2_portal_ready_email_contract())
    findings.extend(pass3_active_subdomain_resolution())
    findings.extend(pass4_tenant_membership_guard())
    findings.extend(pass5_runtime_integration())
    findings.extend(pass6_portal_ready_channels())
    findings.extend(pass7_first_visit_corner_and_nudge())
    findings.extend(pass8_welcome_email_public_host_contract())
    findings.extend(pass9_platform_recovery_cli())

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finding_count": len(findings),
        "passes": 9,
        "findings": findings,
    }
    if args.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    if findings:
        print(f"SIGNUP_PRODUCTION_READINESS_FAIL: {len(findings)} finding(s)")
        for row in findings:
            loc = row.get("path", "")
            print(f"  [{row['pass']}] {loc}: {row['reason']}" if loc else f"  [{row['pass']}] {row['reason']}")
    else:
        print("SIGNUP_PRODUCTION_READINESS_PASS")

    if args.strict and findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
