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
Pass 10 — Owner onboarding done JSON poll + triage_signup_school CLI.
Pass 11 — Render ``SESSION_COOKIE_DOMAIN`` parent-domain contract for cross-host handoff.
Pass 12 — Tenant transactional emails must not default portal links to manager host.
Pass 13 — Pending tenants sign in on slug host; no platform logo on tenant brand mark.

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
        "build_tenant_workspace_login_url",
        "tenant_subdomain_host_exists",
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
        # Mirror signup: usable password + onboarding step stamp = account_ready.
        settings_blob = dict(school.settings or {})
        settings_blob["owner_onboarding"] = {"step": "school"}
        # Ensure Phase B marker so PGL-007 notify gate can fire in this audit harness.
        prov = dict(settings_blob.get("provisioning") or {})
        prov.setdefault("phase_b_complete", True)
        settings_blob["provisioning"] = prov
        school.settings = settings_blob
        school.save(update_fields=["settings"])
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


def pass10_onboarding_poll_and_triage() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    onboarding = ONBOARDING.read_text(encoding="utf-8")
    for needle in (
        "owner_onboarding_provision_status",
        "_kick_provisioning_on_done_page",
        "is_active",
    ):
        if needle not in onboarding:
            findings.append(
                _finding(
                    "pass10",
                    f"owner_onboarding_missing:{needle}",
                    path="apps/accounts/views_owner_onboarding.py",
                )
            )
    urls = REPO_ROOT / "apps" / "accounts" / "urls.py"
    if "owner_onboarding_provision_status" not in urls.read_text(encoding="utf-8"):
        findings.append(
            _finding(
                "pass10",
                "owner_onboarding_provision_status_url_missing",
                path="apps/accounts/urls.py",
            )
        )
    done_tpl = REPO_ROOT / "templates" / "accounts" / "owner_onboarding" / "done.html"
    done_txt = done_tpl.read_text(encoding="utf-8")
    for needle in (
        "rmc_tenant_provision_progress.html",
        "provision_progress_api_url",
    ):
        if needle not in done_txt:
            findings.append(
                _finding(
                    "pass10",
                    f"owner_onboarding_done_template_missing:{needle}",
                    path="templates/accounts/owner_onboarding/done.html",
                )
            )
    poll_js = REPO_ROOT / "static" / "js" / "rmc-tenant-provision-progress.js"
    if not poll_js.is_file():
        findings.append(
            _finding(
                "pass10",
                "rmc_tenant_provision_progress_js_missing",
                path="static/js/rmc-tenant-provision-progress.js",
            )
        )
    elif "progress_percent" not in poll_js.read_text(encoding="utf-8"):
        findings.append(
            _finding(
                "pass10",
                "provisioning_progress_js_must_update_bar",
                path="static/js/rmc-tenant-provision-progress.js",
            )
        )
    triage = (
        REPO_ROOT
        / "apps"
        / "schools"
        / "management"
        / "commands"
        / "triage_signup_school.py"
    )
    if not triage.is_file():
        findings.append(
            _finding(
                "pass10",
                "triage_signup_school_command_missing",
                path="apps/schools/management/commands/triage_signup_school.py",
            )
        )
    else:
        triage_txt = triage.read_text(encoding="utf-8")
        for needle in (
            "lookup_school_by_slug_or_subdomain",
            "activate_pending_signup_schools",
            "signup_completion_was_delivered",
        ):
            if needle not in triage_txt:
                findings.append(
                    _finding(
                        "pass10",
                        f"triage_cli_missing:{needle}",
                        path="apps/schools/management/commands/triage_signup_school.py",
                    )
                )
    boundary = REPO_ROOT / "docs" / "PLATFORM_BOUNDARY_OPERATOR_VS_TENANT.md"
    if boundary.is_file():
        doc = boundary.read_text(encoding="utf-8")
        for needle in (
            "?cp=1",
            "triage_signup_school",
            "onboarding/done/status",
            "slug-first",
        ):
            if needle not in doc:
                findings.append(
                    _finding(
                        "pass10",
                        f"platform_boundary_doc_missing:{needle}",
                        path="docs/PLATFORM_BOUNDARY_OPERATOR_VS_TENANT.md",
                    )
                )
    return findings


def pass11_session_cookie_parent_domain() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    render_yaml = REPO_ROOT / "render.yaml"
    if render_yaml.is_file():
        doc = render_yaml.read_text(encoding="utf-8")
        if "SESSION_COOKIE_DOMAIN" not in doc or ".runmycampus.com" not in doc:
            findings.append(
                _finding(
                    "pass11",
                    "render_yaml_must_set_session_cookie_domain_parent",
                    path="render.yaml",
                )
            )
        if "CSRF_COOKIE_DOMAIN" not in doc:
            findings.append(
                _finding(
                    "pass11",
                    "render_yaml_must_set_csrf_cookie_domain",
                    path="render.yaml",
                )
            )
    env_example = REPO_ROOT / ".env.example"
    if env_example.is_file() and "SESSION_COOKIE_DOMAIN" not in env_example.read_text(
        encoding="utf-8"
    ):
        findings.append(
            _finding(
                "pass11",
                "env_example_should_document_session_cookie_domain",
                path=".env.example",
            )
        )
    return findings


def pass12_tenant_email_no_manager_host() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    reactivation = REPO_ROOT / "apps" / "platform_runtime" / "reactivation_engine.py"
    if reactivation.is_file():
        txt = reactivation.read_text(encoding="utf-8")
        if "manager.runmycampus.com" in txt:
            findings.append(
                _finding(
                    "pass12",
                    "reactivation_engine_must_not_hardcode_manager_host",
                    path="apps/platform_runtime/reactivation_engine.py",
                )
            )
        if "_portal_url_for_reactivation" not in txt:
            findings.append(
                _finding(
                    "pass12",
                    "reactivation_engine_missing_portal_url_helper",
                    path="apps/platform_runtime/reactivation_engine.py",
                )
            )
    for name in (
        "tenant_reactivation_30d.txt",
        "tenant_reactivation_60d.txt",
        "tenant_reactivation_90d.txt",
        "tenant_reactivation_120d.txt",
    ):
        path = REPO_ROOT / "templates" / "emails" / name
        if not path.is_file():
            continue
        if "manager.runmycampus.com" in path.read_text(encoding="utf-8"):
            findings.append(
                _finding(
                    "pass12",
                    "tenant_reactivation_template_defaults_manager_host",
                    path=f"templates/emails/{name}",
                )
            )
    welcome = REPO_ROOT / "apps" / "schools" / "welcome_email.py"
    if welcome.is_file() and "manager.runmycampus.com" in welcome.read_text(encoding="utf-8"):
        findings.append(
            _finding(
                "pass12",
                "welcome_email_must_not_reference_manager_host",
                path="apps/schools/welcome_email.py",
            )
        )
    return findings


def pass13_tenant_workspace_login_and_branding() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    mw = MIDDLEWARE.read_text(encoding="utf-8")
    for needle in (
        "PENDING_TENANT_AUTH_PREFIXES",
        "_bind_pending_school_for_tenant_auth",
        "_path_allows_pending_tenant_auth",
        "APEX_TENANT_AUTH_DISCOVERY_PREFIXES",
        "_apex_auth_path_redirects_to_discovery",
        "/authentication/redirect/",
        "/authentication/school-picker/",
    ):
        if needle not in mw:
            findings.append(
                _finding(
                    "pass13",
                    f"middleware_missing:{needle}",
                    path="apps/schools/middleware.py",
                )
            )
    handoff = (
        REPO_ROOT / "apps" / "schools" / "tenant_login_redirect.py"
    ).read_text(encoding="utf-8")
    if "build_public_handoff_to_tenant_workspace" not in handoff:
        findings.append(
            _finding(
                "pass13",
                "tenant_login_redirect_missing_workspace_handoff",
                path="apps/schools/tenant_login_redirect.py",
            )
        )
    views = (REPO_ROOT / "apps" / "accounts" / "views.py").read_text(encoding="utf-8")
    for needle in ("redirect_to_tenant_workspace", "resolve_public_post_login_handoff"):
        if needle not in views:
            findings.append(
                _finding(
                    "pass13",
                    f"accounts_views_missing:{needle}",
                    path="apps/accounts/views.py",
                )
            )
    brand = (
        REPO_ROOT / "templates" / "components" / "rmc_brand_mark.html"
    ).read_text(encoding="utf-8")
    if "PUBLIC_BRAND_MODE" not in brand or "no platform logo" not in brand.lower():
        findings.append(
            _finding(
                "pass13",
                "rmc_brand_mark_must_gate_platform_logo_on_public_brand_mode",
                path="templates/components/rmc_brand_mark.html",
            )
        )
    provision = (
        REPO_ROOT / "apps" / "schools" / "provision_email_urls.py"
    ).read_text(encoding="utf-8")
    if "build_tenant_workspace_login_url" not in provision:
        findings.append(
            _finding(
                "pass13",
                "provision_email_urls_missing_workspace_login_builder",
                path="apps/schools/provision_email_urls.py",
            )
        )
    if "build_public_discovery_url" not in provision:
        findings.append(
            _finding(
                "pass13",
                "provision_email_urls_missing_public_discovery_builder",
                path="apps/schools/provision_email_urls.py",
            )
        )
    for prefix in ("/authentication/oidc", "/authentication/saml"):
        if prefix not in mw:
            findings.append(
                _finding(
                    "pass13",
                    f"apex_discovery_missing_sso_prefix:{prefix}",
                    path="apps/schools/middleware.py",
                )
            )
    return findings


def pass14_customer_progress_component() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    partial = REPO_ROOT / "templates" / "components" / "rmc_tenant_provision_progress.html"
    js = REPO_ROOT / "static" / "js" / "rmc-tenant-provision-progress.js"
    if not partial.is_file():
        findings.append(_finding("pass14", "rmc_tenant_provision_progress_partial_missing", path=str(partial)))
    if not js.is_file():
        findings.append(_finding("pass14", "rmc_tenant_provision_progress_js_missing", path=str(js)))
    done = REPO_ROOT / "templates" / "accounts" / "owner_onboarding" / "done.html"
    if partial.is_file() and partial.name not in done.read_text(encoding="utf-8"):
        findings.append(_finding("pass14", "owner_onboarding_done_missing_progress_partial", path="templates/accounts/owner_onboarding/done.html"))
    return findings


def pass15_status_api_parity() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    resolver = REPO_ROOT / "apps" / "schools" / "provisioning_progress.py"
    if not resolver.is_file():
        findings.append(_finding("pass15", "provisioning_progress_resolver_missing", path=str(resolver)))
        return findings
    rtxt = resolver.read_text(encoding="utf-8")
    for needle in ("progress_percent", "current_step_label", "workflow_run_id", "steps"):
        if needle not in rtxt:
            findings.append(_finding("pass15", f"resolver_missing:{needle}", path="apps/schools/provisioning_progress.py"))
    onboarding = ONBOARDING.read_text(encoding="utf-8")
    tenant = (REPO_ROOT / "apps" / "lifecycle" / "views_tenant_lifecycle.py").read_text(encoding="utf-8")
    if "resolve_provisioning_progress" not in onboarding:
        findings.append(_finding("pass15", "owner_api_must_call_resolver", path="apps/accounts/views_owner_onboarding.py"))
    if "resolve_provisioning_progress" not in tenant:
        findings.append(_finding("pass15", "tenant_api_must_call_resolver", path="apps/lifecycle/views_tenant_lifecycle.py"))
    urls = REPO_ROOT / "apps" / "accounts" / "urls.py"
    if "owner_onboarding_provision_progress" not in urls.read_text(encoding="utf-8"):
        findings.append(_finding("pass15", "owner_progress_url_missing", path="apps/accounts/urls.py"))
    return findings


def pass16_workflow_registry_steps() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    registry = (REPO_ROOT / "apps" / "platform_runtime" / "workflow_registry.py").read_text(encoding="utf-8")
    progress = (REPO_ROOT / "apps" / "schools" / "provisioning_progress.py").read_text(encoding="utf-8")
    for step in ("admin_user", "profile", "tenant_schema", "seed_data", "activate"):
        if step not in registry or step not in progress:
            findings.append(_finding("pass16", f"step_missing:{step}", path="apps/schools/provisioning_progress.py"))
    return findings


def pass17_owner_apply_fix_route() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    urls = REPO_ROOT / "apps" / "accounts" / "urls.py"
    onboarding = ONBOARDING.read_text(encoding="utf-8")
    if "owner_onboarding_provision_apply_fix" not in urls.read_text(encoding="utf-8"):
        findings.append(_finding("pass17", "apply_fix_url_missing", path="apps/accounts/urls.py"))
    if "owner_onboarding_provision_apply_fix" not in onboarding:
        findings.append(_finding("pass17", "apply_fix_view_missing", path="apps/accounts/views_owner_onboarding.py"))
    handlers = (REPO_ROOT / "apps" / "platform_runtime" / "workflow_fix_handlers.py").read_text(encoding="utf-8")
    if "requeue_provision" not in handlers:
        findings.append(_finding("pass17", "requeue_provision_handler_missing", path="apps/platform_runtime/workflow_fix_handlers.py"))
    return findings


def pass18_failed_run_human_action() -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    auto_fix = (REPO_ROOT / "apps" / "platform_runtime" / "workflow_auto_fix.py").read_text(encoding="utf-8")
    progress = (REPO_ROOT / "apps" / "schools" / "provisioning_progress.py").read_text(encoding="utf-8")
    partial = (REPO_ROOT / "templates" / "components" / "rmc_tenant_provision_progress.html").read_text(encoding="utf-8")
    if "human_action" not in auto_fix or "human_action" not in progress:
        findings.append(_finding("pass18", "human_action_contract_missing", path="apps/schools/provisioning_progress.py"))
    if "data-rmc-copilot-context" not in partial:
        findings.append(_finding("pass18", "copilot_context_marker_missing", path="templates/components/rmc_tenant_provision_progress.html"))
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
    findings.extend(pass10_onboarding_poll_and_triage())
    findings.extend(pass11_session_cookie_parent_domain())
    findings.extend(pass12_tenant_email_no_manager_host())
    findings.extend(pass13_tenant_workspace_login_and_branding())
    findings.extend(pass14_customer_progress_component())
    findings.extend(pass15_status_api_parity())
    findings.extend(pass16_workflow_registry_steps())
    findings.extend(pass17_owner_apply_fix_route())
    findings.extend(pass18_failed_run_human_action())

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finding_count": len(findings),
        "passes": 18,
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
