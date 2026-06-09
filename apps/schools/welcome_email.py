"""
Phase Welcome: Welcome email after school provisioning.
HTML template with tenant branding (primary_color, logo_url) and dynamic block (Trade vs General).
Triggered post-provisioning; sent via Celery to avoid blocking.
Optional: regional SMTP — set Django EMAIL_BACKEND / use SES Frankfurt etc. per region (e.g. in settings or env).
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.utils.html import escape

logger = logging.getLogger(__name__)


def _regional_from_email(school) -> str:
    """Optional regional SMTP: from_email by school region (e.g. EU → Frankfurt)."""
    default = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")
    region_map = getattr(settings, "REGIONAL_FROM_EMAIL", None)
    if not region_map or not isinstance(region_map, dict):
        return default
    region_id = getattr(school, "default_region_id", None) or ""
    return region_map.get(region_id) or region_map.get(str(region_id)) or default


def _login_url(school) -> str:
    """Login URL on the public site (subdomain login 404s until DNS + is_active)."""
    from apps.schools.provision_email_urls import build_public_login_url

    return build_public_login_url()


def render_welcome_email_html(
    school,
    contact_email: str,
    *,
    login_url: str | None = None,
    setup_password_url: str | None = None,
    dynamic_block: str = "",
) -> str:
    """
    Build HTML body with tenant branding (primary_color, logo_url) and optional dynamic block.
    Trade vs General: pass dynamic_block from profile (e.g. "Workshop Setup Guide" vs "Gradebook Configuration").
    """
    try:
        from apps.siteconfig.branding import resolve_brand_profile
        from apps.siteconfig.config_service import get_effective_site_settings

        brand = resolve_brand_profile(
            school=school, site=get_effective_site_settings(school=school)
        )
    except (ImportError, AttributeError, TypeError, ValueError, KeyError) as e:
        logger.debug(
            "Welcome email brand resolve fallback for school %s: %s",
            getattr(school, "id", None),
            e,
        )
        brand = {}
    # Escape every interpolated value (audit P2 — HTML/attribute injection).
    # ``primary`` lands inside style/href attributes; ``name`` / ``contact_email``
    # are tenant-controlled. ``block`` is platform-authored profile config
    # (trusted markup), so it is intentionally NOT escaped.
    primary = escape(
        brand.get("primary_color")
        or getattr(school, "primary_color", None)
        or "#0d6efd"
    )
    _logo_url = brand.get("logo_url") or getattr(school, "logo_url", None) or ""
    name = escape(getattr(school, "name", None) or "Your School")
    contact_email = escape(contact_email)
    login = escape(login_url or _login_url(school))
    setup = escape((setup_password_url or "").strip())
    block = (dynamic_block or "").strip()
    setup_cta = ""
    if setup:
        setup_cta = (
            f'<p style="margin: 1rem 0;">'
            f'<a href="{setup}" style="background: {primary}; color: #fff; padding: 0.5rem 1rem; '
            f'text-decoration: none; border-radius: 4px;">Set your password</a>'
            f"</p>"
            f'<p style="color: #666; font-size: 0.9rem;">This link expires in a few days. '
            f"After you set a password, sign in at "
            f'<a href="{login}">{login}</a>.</p>'
        )
    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Welcome to {name}</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 600px; margin: 0 auto; padding: 1rem;">
  <div style="border-left: 4px solid {primary}; padding-left: 1rem;">
    <h1 style="color: {primary};">Your school is ready!</h1>
    <p>Welcome to {name}. Your school has been set up for <strong>{contact_email}</strong>.</p>
    {setup_cta if setup_cta else f'<p><a href="{login}" style="background: {primary}; color: #fff; padding: 0.5rem 1rem; text-decoration: none; border-radius: 4px;">Open sign-in</a></p>'}
    {f'<div style="margin-top: 1rem;">{block}</div>' if block else ""}
    <p style="color: #666; font-size: 0.9rem;">If you did not request this, please ignore this email.</p>
  </div>
</body>
</html>
"""


def send_welcome_email(school_id: str, contact_email: str) -> bool:
    """
    Send welcome email to contact_email after provisioning. Uses tenant branding.
    Returns True if sent, False if skipped (no email, no school, or send failure).
    """
    if not (contact_email or "").strip():
        return False
    from apps.schools.models import School

    school = School.objects.filter(id=school_id).first()
    if not school:
        return False
    from apps.siteconfig.education_profile_engine import resolve_profile_for_school

    profile = resolve_profile_for_school(
        school, requested_profile_code="", auto_create=False
    )
    dynamic_block = ""
    if profile and getattr(profile, "config", None):
        cfg = profile.config
        if isinstance(cfg, dict) and cfg.get("welcome_block"):
            dynamic_block = str(cfg["welcome_block"])
    setup_password_url = ""
    login_url_override = None
    from django.contrib.auth import get_user_model

    admin_user = (
        get_user_model()
        .objects.filter(email__iexact=contact_email.strip())
        .order_by("pk")
        .first()
    )
    if admin_user:
        account_ready = admin_user.has_usable_password()
        if getattr(school, "is_active", False) and account_ready:
            from apps.schools.provision_email_urls import (
                build_tenant_authentication_url,
            )

            login_url_override = build_tenant_authentication_url(
                school, "/authentication/login/"
            )
        elif not account_ready:
            try:
                from apps.schools.provision_email_urls import build_owner_onboarding_url

                setup_password_url = build_owner_onboarding_url(school, admin_user)
            except (ImportError, AttributeError, TypeError, ValueError):
                setup_password_url = ""
            if not setup_password_url:
                from apps.schools.provision_email_urls import (
                    build_provision_setup_password_url,
                )

                setup_password_url = build_provision_setup_password_url(
                    school, admin_user
                )
    html = render_welcome_email_html(
        school,
        contact_email,
        dynamic_block=dynamic_block,
        setup_password_url=setup_password_url or None,
        login_url=login_url_override,
    )
    subject = f"Your school is ready — {getattr(school, 'name', 'Your School')}"
    from_email = _regional_from_email(school)
    # Route through the reliability layer (audit H1): retried, rate-limited,
    # audited to EmailDeliveryEvent, recipient hashed in logs. A short plain-
    # text body accompanies the HTML for non-HTML clients + deliverability.
    text_body = (
        f"Welcome to {getattr(school, 'name', 'Your School')}. Your school is "
        f"ready. Sign in at {_login_url(school)}"
    )
    try:
        from apps.schoolops.email_delivery import send_transactional

        result = send_transactional(
            subject=subject,
            body=text_body,
            to=[contact_email.strip()],
            html_body=html,
            from_email=from_email,
            priority="transactional",
            school=school,
            idempotency_key=f"welcome:{school_id}:{contact_email.strip().lower()}",
        )
        return bool(result.get("ok") or result.get("queued"))
    except Exception as e:  # noqa: BLE001 — never break provisioning on mail
        logger.warning("Welcome email failed for school %s: %s", school_id, type(e).__name__)
        return False


try:
    from celery import shared_task

    @shared_task(bind=True, max_retries=2)
    def send_welcome_email_task(self, school_id: str, contact_email: str = ""):
        """Phase Welcome: Celery task to send welcome email after provisioning."""
        if not send_welcome_email(school_id, contact_email):
            return
except ImportError:

    def send_welcome_email_task(*args, **kwargs):
        """No-op when Celery not installed; provisioning code calls send_welcome_email synchronously."""
        pass
