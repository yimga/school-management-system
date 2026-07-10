"""
Shared helpers and constants for finance views (§6.15 app-by-app split).
Used by views_dashboard, views_invoicing, views_payments, views_access,
views_accounting, views_requests. Single place for runtime/settings resolution.
"""

from __future__ import annotations

import logging
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError
from django.http import HttpRequest
from django.conf import settings
from django.urls import reverse

from services.post_delete_navigation import (
    redirect_after_detail_mutation,
    redirect_after_save,
)

from apps.platform_runtime.config_resolver import get_effective_config
from apps.siteconfig.config_service import (
    get_effective_flags,
    get_effective_site_settings,
)

from .models import ComplianceProfile, Notification, FinanceRequestAudit

logger = logging.getLogger(__name__)

FINANCE_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    IntegrityError,
    LookupError,
    RuntimeError,
    TypeError,
    ValidationError,
    ValueError,
)


def _active_profile(request: HttpRequest | None = None) -> ComplianceProfile | None:
    profile = get_effective_config(key="compliance_profile", request=request)
    if profile is not None:
        return profile
    profile_id = get_effective_config(key="compliance_profile_id", request=request)
    if profile_id is not None:
        try:
            resolved = ComplianceProfile.objects.filter(pk=int(profile_id)).first()
        except (TypeError, ValueError):
            resolved = None
        if resolved is not None:
            return resolved
    return ComplianceProfile.objects.filter(is_active=True).first()


def _backend_flags(request: HttpRequest | None = None) -> dict:
    """
    Convenience wrapper to merge default backend flags with saved settings.
    Safe for use in early request handling where DB might be missing values.
    """
    try:
        return get_effective_flags(request)
    except FINANCE_SOFT_FAILURES:
        return {}


def _notification_delivery_settings(
    request: HttpRequest | None = None,
    *,
    site=None,
) -> tuple[list[str], str | None]:
    """
    Resolve notification channels and sender identity through owner-scoped settings.
    """
    # config-resolver-allow: namespace method get_notification_delivery_settings() is invoked (not a plain key read)
    current_site = site or get_effective_site_settings(request=request)
    feature_settings = (
        current_site.get_notification_delivery_settings()
        if callable(getattr(current_site, "get_notification_delivery_settings", None))
        else {}
    )
    channels = list(feature_settings.get("notification_channels") or [])
    from_email = feature_settings.get("email_from_address") or getattr(
        settings, "DEFAULT_FROM_EMAIL", None
    )
    return channels, from_email


def _finance_access_state(user, request: HttpRequest | None = None) -> dict:
    """
    Snapshot of finance access for a guardian user.
    Returns counts, whether opt-in is required, and whether requests are allowed.
    """
    from apps.accounts.permissions import _guardian_finance_qs
    from apps.people.models import StudentGuardian

    flags = _backend_flags(request)
    guardian_qs = StudentGuardian.objects.filter(guardian_user=user)
    finance_qs = (
        _guardian_finance_qs(user)
        if getattr(user, "is_authenticated", False)
        else StudentGuardian.objects.none()
    )
    return {
        "require_opt_in": bool(flags.get("require_guardian_finance_opt_in")),
        "allow_requests": bool(flags.get("allow_finance_access_requests", True)),
        "guardian_count": guardian_qs.count(),
        "finance_count": finance_qs.count(),
        "guardian_names": [
            str(link.student) for link in guardian_qs.select_related("student")
        ],
    }


def _log_finance_request_audit(
    notification: Notification | None, user, action: str, details: str = ""
) -> None:
    if not notification:
        return
    FinanceRequestAudit.objects.create(
        notification=notification,
        user=user,
        action=action,
        details=details or "",
    )


def _create_finance_request_notification(
    recipient,
    *,
    title: str,
    message: str,
    severity: str,
    created_by,
    action: str,
    details: str = "",
) -> Notification:
    notif = Notification.objects.notify_unread(
        title=title,
        message=message,
        severity=severity,
        recipient=recipient,
        created_by=created_by,
    )
    _log_finance_request_audit(notif, created_by, action, details)
    return notif


def _notify_finance_staff_suspicious_receipt(proof_upload, fraud_result: dict) -> None:
    """Notify finance staff when suspicious receipt is uploaded."""
    from apps.accounts.models import User
    from apps.evals.notifications import NotificationService

    try:
        finance_staff = User.objects.filter(
            is_staff=True,
            groups__name__in=["Finance", "Bursar", "Accountant"],
        ).distinct()
        if not finance_staff.exists():
            finance_staff = User.objects.filter(is_staff=True, is_superuser=False)

        notification_service = NotificationService()
        fraud_flags_str = ", ".join(fraud_result.get("fraud_flags", []))
        message = (
            f"⚠️ SUSPICIOUS RECEIPT UPLOADED\n\n"
            f"Invoice: {proof_upload.invoice.reference or proof_upload.invoice.id}\n"
            f"Student: {proof_upload.invoice.student}\n"
            f"Uploaded by: {proof_upload.uploaded_by.get_full_name() if proof_upload.uploaded_by else 'Unknown'}\n"
            f"Amount: {proof_upload.uploaded_amount or 'Not specified'}\n"
            f"Fraud Risk Score: {fraud_result.get('fraud_risk_score', 0)}/100\n"
            f"Flags: {fraud_flags_str}\n"
            f"Recommendation: {fraud_result.get('recommendation', 'review').upper()}\n\n"
            f"Please review immediately: /admin/finance/paymentproofupload/{proof_upload.id}/change/"
        )
        for staff_member in finance_staff[:10]:
            try:
                notification_service.send_notification(
                    user=staff_member,
                    title="🚨 Suspicious Receipt Upload",
                    message=message,
                    channels=["email"],
                )
            except FINANCE_SOFT_FAILURES as e:
                logger.error(
                    "Failed to notify finance staff %s: %s", staff_member.id, e
                )
    except FINANCE_SOFT_FAILURES as e:
        logger.error("Error notifying finance staff about suspicious receipt: %s", e)


def _can_access_accounting(user) -> bool:
    """Accountant role or accounting.view permission (Bursar entries, expense vs budget)."""
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_superuser", False):
        return True
    role = (getattr(user, "role", "") or "").upper()
    if role == "ACCOUNTANT":
        return True
    return getattr(user, "has_feature_permission", lambda _: False)("accounting.view")


def finance_save_redirect(request: HttpRequest, url_name: str, **url_kwargs):
    """Return to a finance list/hub after save, preserving ``next`` / referer filters."""
    url = reverse(url_name, kwargs=url_kwargs) if url_kwargs else reverse(url_name)
    return redirect_after_save(request, url, list_url=url)


def finance_detail_redirect(request: HttpRequest, invoice_id):
    """Stay on invoice detail after in-place mutations."""
    url = reverse("finance:invoice_detail", kwargs={"invoice_id": invoice_id})
    return redirect_after_detail_mutation(request, url)
