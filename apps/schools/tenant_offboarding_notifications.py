"""Email notifications for tenant offboarding (platform + school admins)."""

from __future__ import annotations

import logging
import os
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def notifications_enabled() -> bool:
    return _env_bool("TENANT_OFFBOARDING_EMAIL_ENABLED", "1")


def notify_tenant_admins_enabled() -> bool:
    return _env_bool("TENANT_OFFBOARDING_NOTIFY_TENANT_ADMINS", "1")


def platform_notification_emails() -> list[str]:
    raw = (
        os.environ.get("TENANT_OFFBOARDING_PLATFORM_EMAILS", "").strip()
        or os.environ.get("OPERATOR_ALERT_EMAIL", "").strip()
        or os.environ.get("MIGRATION_CLOUD_OPERATOR_ALERT_EMAIL", "").strip()
    )
    if raw:
        return [e.strip() for e in raw.split(",") if e.strip()]
    admins = getattr(settings, "ADMINS", None) or []
    return [email for _name, email in admins if email]


def school_admin_emails(school) -> list[str]:
    from apps.schools.models import SchoolMembership

    emails: list[str] = []
    qs = (
        SchoolMembership.objects.filter(school=school, role="ADMIN")
        .select_related("user")
        .order_by("-is_primary", "id")[:20]
    )
    for membership in qs:
        user = membership.user
        email = (getattr(user, "email", None) or "").strip()
        if email and email not in emails:
            emails.append(email)
    off = (getattr(school, "settings", None) or {}).get("offboarding") or {}
    if isinstance(off, dict):
        extra = (off.get("notify_email") or "").strip()
        if extra and extra not in emails:
            emails.append(extra)
    return emails


def _manager_tenant_360_url(school) -> str:
    base = (
        os.environ.get("MANAGER_PLATFORM_BASE_URL", "").strip()
        or getattr(settings, "MANAGER_PLATFORM_BASE_URL", "")
        or "https://manager.runmycampus.com"
    ).rstrip("/")
    return f"{base}/super/tenants/{school.id}/360/#offboarding"


def _queue_url() -> str:
    base = (
        os.environ.get("MANAGER_PLATFORM_BASE_URL", "").strip()
        or getattr(settings, "MANAGER_PLATFORM_BASE_URL", "")
        or "https://manager.runmycampus.com"
    ).rstrip("/")
    return f"{base}/super/offboarding/"


def _send(recipients: list[str], subject: str, body: str, *, school: Any = None) -> None:
    if not notifications_enabled() or not recipients:
        return
    try:
        from apps.communication.notification_service import send_email
    except ImportError:
        logger.warning("tenant_offboarding notify skipped: notification_service unavailable")
        return
    send_email(recipients, subject, body, school=school, fail_silently=True)


def notify_offboarding_request_submitted(
    school, *, actor, reason: str = ""
) -> None:
    slug = school.slug
    name = school.name
    actor_label = getattr(actor, "username", "") or "school-admin"
    body = (
        f"School '{name}' ({slug}) submitted an offboarding REQUEST (operator approval required).\n"
        f"Requested by: {actor_label}\n"
        f"Reason: {(reason or '—')[:200]}\n"
        f"Approve from Offboarding queue or Tenant 360.\n"
        f"Tenant 360: {_manager_tenant_360_url(school)}\n"
        f"Offboarding queue: {_queue_url()}\n"
    )
    _send(
        platform_notification_emails(),
        f"[RunMyCampus] Offboarding request pending approval — {slug}",
        body,
        school=school,
    )
    if notify_tenant_admins_enabled():
        tenant_body = (
            f"Your offboarding request for '{name}' was received.\n"
            f"Platform operations will review and approve before any deactivation or purge schedule.\n"
            f"You may withdraw the request from School Studio while it is still pending.\n"
        )
        _send(
            school_admin_emails(school),
            f"Offboarding request received — {name}",
            tenant_body,
            school=school,
        )


def notify_self_service_closure_requested(
    school, *, actor, scheduled_purge_at: str
) -> None:
    slug = school.slug
    name = school.name
    actor_label = getattr(actor, "username", "") or "school-admin"
    body = (
        f"School '{name}' ({slug}) requested self-service account closure.\n"
        f"Requested by: {actor_label}\n"
        f"Scheduled purge date: {scheduled_purge_at}\n"
        f"Tenant 360: {_manager_tenant_360_url(school)}\n"
        f"Offboarding queue: {_queue_url()}\n"
    )
    platform_subject = f"[RunMyCampus] Tenant closure requested — {slug}"
    _send(platform_notification_emails(), platform_subject, body, school=school)
    if notify_tenant_admins_enabled():
        tenant_body = (
            f"This confirms your request to close the school account '{name}'.\n"
            f"Access is deactivated. Data export remains available before "
            f"scheduled removal on {scheduled_purge_at}.\n"
            f"To cancel before that date, open School Studio → Close school account.\n"
        )
        _send(
            school_admin_emails(school),
            f"Account closure scheduled — {name}",
            tenant_body,
            school=school,
        )


def notify_self_service_closure_cancelled(school, *, actor) -> None:
    slug = school.slug
    body = (
        f"Self-service closure cancelled for '{school.name}' ({slug}).\n"
        f"Cancelled by: {getattr(actor, 'username', '') or 'operator'}\n"
    )
    _send(
        platform_notification_emails(),
        f"[RunMyCampus] Tenant closure cancelled — {slug}",
        body,
        school=school,
    )


def notify_operator_purge_scheduled(school, *, actor, purge_at: str) -> None:
    body = (
        f"Operator scheduled purge for '{school.name}' ({school.slug}) on {purge_at}.\n"
        f"By: {getattr(actor, 'username', '') or 'operator'}\n"
        f"Tenant 360: {_manager_tenant_360_url(school)}\n"
    )
    _send(
        platform_notification_emails(),
        f"[RunMyCampus] Tenant purge scheduled — {school.slug}",
        body,
        school=school,
    )


def notify_purge_completed(receipt: Any, *, purge_source: str = "operator") -> None:
    cert_note = ""
    try:
        from apps.lifecycle.models_purge import PurgeOperation

        op = (
            PurgeOperation.objects.filter(school_slug=receipt.school_slug)
            .order_by("-completed_at")
            .first()
        )
        if op and op.certificate_signature:
            cert_note = (
                f"\nDeletion certificate: purge_operation_id={op.id} "
                f"signature={op.certificate_signature[:24]}…\n"
            )
    except Exception:
        pass
    body = (
        f"Permanent purge completed ({purge_source}).\n"
        f"School: {receipt.school_slug}\n"
        f"Rows removed: {receipt.row_total}\n"
        f"Manifest: {receipt.manifest_path}\n"
        f"{cert_note}"
    )
    _send(
        platform_notification_emails(),
        f"[RunMyCampus] Tenant purged — {receipt.school_slug}",
        body,
    )


def notify_scheduled_purge_batch(*, processed: list[dict], dry_run: bool) -> None:
    if not processed:
        return
    lines = []
    for entry in processed[:25]:
        slug = entry.get("school_slug", "?")
        if entry.get("purged"):
            lines.append(f"  - PURGED {slug}")
        elif entry.get("skipped"):
            lines.append(f"  - SKIPPED {slug}: {entry.get('blockers')}")
        elif dry_run:
            lines.append(f"  - DRY-RUN {slug}: {entry.get('row_total')} rows")
    body = (
        f"Scheduled tenant purge run (dry_run={dry_run}).\n"
        + "\n".join(lines)
        + f"\nQueue: {_queue_url()}\n"
    )
    _send(
        platform_notification_emails(),
        "[RunMyCampus] Scheduled tenant purge summary",
        body,
    )
