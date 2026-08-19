"""Guardian / parent account-activation invite.

A parent account created from student onboarding (online OR via the offline
drain) gets an UNUSABLE password and, until now, no way to set one: the standard
portal password-reset flow excludes unusable-password users
(``PortalPasswordResetForm.get_users`` filters on ``has_usable_password``), so an
invited guardian was silently locked out.

This module issues a one-time "set your password" link that DOES work for an
unusable-password account, reusing Django's password-reset token machinery
(time-bounded by ``PASSWORD_RESET_TIMEOUT``, single-use). The actual email
delivery rides the audited ``send_transactional`` reliability layer; whether it
leaves the building depends on the platform mail relay (an external dependency),
but the link generation + audited send are the internal contract.
"""
from __future__ import annotations

import logging

from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import PasswordResetConfirmView
from django.urls import reverse, reverse_lazy
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.accounts.email_delivery_policy import is_deliverable_email

logger = logging.getLogger(__name__)


def build_guardian_setup_link(user, *, request=None, base_url: str = "") -> str:
    """Return a set-password URL for ``user``.

    Absolute when a ``request`` (online) or ``base_url`` (offline drain) is
    available; otherwise a site-relative path (still recorded, just not
    click-ready in an email).
    """
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse(
        "accounts:guardian_setup", kwargs={"uidb64": uidb64, "token": token}
    )
    if request is not None:
        return request.build_absolute_uri(path)
    if base_url:
        return base_url.rstrip("/") + path
    return path


def _resolve_base_url(request) -> str:
    if request is not None:
        return ""  # request path is used directly
    try:
        from apps.schools.host_routing import get_canonical_base_domain

        host = (get_canonical_base_domain() or "").strip()
        if host:
            return host if host.startswith("http") else f"https://{host}"
    except Exception:  # noqa: BLE001 — base-URL resolution is best-effort only
        pass
    return ""


def send_guardian_invite(user, *, request=None, school=None) -> dict:
    """Best-effort: email ``user`` a one-time set-password link.

    Returns ``{"sent": bool, "link": str, "reason": str}``. NEVER raises —
    credential delivery must not break the (online or offline-drain) creation
    flow that triggered it.
    """
    if user is None or not getattr(user, "pk", None):
        return {"sent": False, "link": "", "reason": "no_user"}
    email = (getattr(user, "email", "") or "").strip()
    if not email:
        return {"sent": False, "link": "", "reason": "no_email"}
    if not is_deliverable_email(email):
        return {"sent": False, "link": "", "reason": "undeliverable_email"}

    link = build_guardian_setup_link(
        user, request=request, base_url=_resolve_base_url(request)
    )
    school_name = (getattr(school, "name", "") or "Your school").strip() or "Your school"
    subject = "Set up your RunMyCampus parent account"
    body = (
        f"{school_name} created a parent account for you on RunMyCampus.\n\n"
        f"Set your password to sign in:\n{link}\n\n"
        "This link is valid for a limited time and can be used once."
    )
    try:
        from apps.schoolops.email_delivery import send_transactional

        send_transactional(
            subject=subject,
            body=body,
            to=[email],
            priority="transactional",
            allow_suppressed=True,
        )
        logger.info("accounts.guardian_invite.sent user_id=%s", user.pk)
        return {"sent": True, "link": link, "reason": "queued"}
    except Exception as exc:  # noqa: BLE001 — delivery must never break creation
        logger.warning(
            "accounts.guardian_invite.send_failed user_id=%s err_type=%s",
            user.pk, type(exc).__name__,
        )
        return {"sent": False, "link": link, "reason": "send_failed"}


class GuardianSetupView(PasswordResetConfirmView):
    """Set-password landing for invited guardians.

    Reuses Django's :class:`PasswordResetConfirmView` token validation (battle
    tested, time-bounded, single-use) — which, unlike the portal reset *form*,
    works for an unusable-password account. ``form_valid`` additionally activates
    the account if it was inactive, so a single click both sets the password and
    enables sign-in. URL: ``/accounts/guardian-setup/<uidb64>/<token>/``.
    """

    template_name = "accounts/guardian_setup.html"
    success_url = reverse_lazy("accounts:login")

    def get_user(self, uidb64):
        # Role gate: this generic "set password + activate" flow must only ever
        # apply to PARENT/guardian accounts. get_user() is how
        # PasswordResetConfirmView resolves the token's user; returning None makes
        # the link present as invalid/expired. This guarantees a token minted for
        # a deactivated staff/admin can never re-activate them via this view.
        user = super().get_user(uidb64)
        if user is not None:
            from apps.accounts.models import User as _User

            if getattr(user, "role", None) != _User.Role.PARENT:
                logger.warning(
                    "guardian_setup_role_refused",
                    extra={"user_id": getattr(user, "pk", None)},
                )
                return None  # → token treated as invalid; "link expired" page
        return user

    def form_valid(self, form):
        response = super().form_valid(form)
        user = getattr(self, "user", None)
        if user is not None and not user.is_active:
            user.is_active = True
            try:
                user.save(update_fields=["is_active"])
            except Exception:  # noqa: BLE001 — activation failure must not break setup
                logger.exception(
                    "guardian_setup_activate_failed", extra={"user_id": user.pk}
                )
        if user is not None:
            logger.info(
                "guardian_setup_complete",
                extra={"user_id": user.pk, "result": "password_set"},
            )
        return response


def build_staff_setup_link(user, *, request=None, base_url: str = "") -> str:
    """Set-password URL for a migrated teacher (unusable password until first login)."""
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse(
        "accounts:staff_setup", kwargs={"uidb64": uidb64, "token": token}
    )
    if request is not None:
        return request.build_absolute_uri(path)
    if base_url:
        return base_url.rstrip("/") + path
    return path


def send_staff_setup_invite(user, *, request=None, school=None) -> dict:
    """Email a migrated teacher a one-time set-password link. Never raises."""
    if user is None or not getattr(user, "pk", None):
        return {"sent": False, "link": "", "reason": "no_user"}
    email = (getattr(user, "email", "") or "").strip()
    if not email:
        return {"sent": False, "link": "", "reason": "no_email"}
    if not is_deliverable_email(email):
        return {"sent": False, "link": "", "reason": "undeliverable_email"}

    link = build_staff_setup_link(
        user, request=request, base_url=_resolve_base_url(request)
    )
    school_name = (getattr(school, "name", "") or "Your school").strip() or "Your school"
    subject = "Set up your RunMyCampus staff account"
    body = (
        f"{school_name} created a staff account for you on RunMyCampus.\n\n"
        f"Set your password to sign in, then complete your profile:\n{link}\n\n"
        "This link is valid for a limited time and can be used once."
    )
    try:
        from apps.schoolops.email_delivery import send_transactional

        send_transactional(
            subject=subject,
            body=body,
            to=[email],
            priority="transactional",
            allow_suppressed=True,
        )
        logger.info("accounts.staff_setup_invite.sent user_id=%s", user.pk)
        return {"sent": True, "link": link, "reason": "queued"}
    except Exception as exc:  # noqa: BLE001 — delivery must never break activation
        logger.warning(
            "accounts.staff_setup_invite.send_failed user_id=%s err_type=%s",
            user.pk,
            type(exc).__name__,
        )
        return {"sent": False, "link": link, "reason": "send_failed"}


class StaffSetupView(PasswordResetConfirmView):
    """Set-password landing for invited/migrated staff. Parents/students refused."""

    template_name = "accounts/staff_setup.html"
    success_url = reverse_lazy("accounts:login")

    def get_user(self, uidb64):
        user = super().get_user(uidb64)
        if user is not None:
            from apps.migration_cloud.staff_role_map import is_staff_setup_role

            if not is_staff_setup_role(getattr(user, "role", None)):
                logger.warning(
                    "staff_setup_role_refused",
                    extra={"user_id": getattr(user, "pk", None)},
                )
                return None
        return user

    def form_valid(self, form):
        response = super().form_valid(form)
        user = getattr(self, "user", None)
        if user is not None and not user.is_active:
            user.is_active = True
            try:
                user.save(update_fields=["is_active"])
            except Exception:  # noqa: BLE001
                logger.exception(
                    "staff_setup_activate_failed", extra={"user_id": user.pk}
                )
        if user is not None:
            try:
                user.requires_password_change = False
                user.save(update_fields=["requires_password_change"])
            except Exception:  # noqa: BLE001
                logger.exception(
                    "staff_setup_flag_failed", extra={"user_id": user.pk}
                )
            logger.info(
                "staff_setup_complete",
                extra={"user_id": user.pk, "result": "password_set"},
            )
        return response
