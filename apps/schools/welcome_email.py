"""
Phase Welcome: Welcome email after school provisioning.
HTML template with tenant branding (primary_color, logo_url) and dynamic block (Trade vs General).
Triggered post-provisioning; sent via Celery to avoid blocking.
Optional: regional SMTP — set Django EMAIL_BACKEND / use SES Frankfurt etc. per region (e.g. in settings or env).
"""
from __future__ import annotations

import logging
from django.conf import settings
from django.core.mail import EmailMessage

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
    """Login URL for the school (subdomain or main)."""
    from django.urls import reverse
    base = getattr(settings, "BASE_URL", "") or ""
    if base:
        return f"{base.rstrip('/')}/accounts/login/"
    return reverse("accounts:login")


def render_welcome_email_html(
    school,
    contact_email: str,
    *,
    login_url: str | None = None,
    dynamic_block: str = "",
) -> str:
    """
    Build HTML body with tenant branding (primary_color, logo_url) and optional dynamic block.
    Trade vs General: pass dynamic_block from profile (e.g. "Workshop Setup Guide" vs "Gradebook Configuration").
    """
    try:
        from apps.siteconfig.branding import resolve_brand_profile
        from apps.siteconfig.models import SiteSettings

        brand = resolve_brand_profile(school=school, site=SiteSettings.get_solo())
    except Exception:
        brand = {}
    primary = brand.get("primary_color") or getattr(school, "primary_color", None) or "#0d6efd"
    logo_url = brand.get("logo_url") or getattr(school, "logo_url", None) or ""
    name = getattr(school, "name", None) or "Your School"
    login = login_url or _login_url(school)
    block = (dynamic_block or "").strip()
    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Welcome to {name}</title></head>
<body style="font-family: system-ui, sans-serif; max-width: 600px; margin: 0 auto; padding: 1rem;">
  <div style="border-left: 4px solid {primary}; padding-left: 1rem;">
    <h1 style="color: {primary};">Your school is ready!</h1>
    <p>Welcome to {name}. Your school has been set up. You can log in with this email address.</p>
    <p><a href="{login}" style="background: {primary}; color: #fff; padding: 0.5rem 1rem; text-decoration: none; border-radius: 4px;">Open dashboard</a></p>
    {f'<div style="margin-top: 1rem;">{block}</div>' if block else ''}
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
    profile = resolve_profile_for_school(school, requested_profile_code="", auto_create=False)
    dynamic_block = ""
    if profile and getattr(profile, "config", None):
        cfg = profile.config
        if isinstance(cfg, dict) and cfg.get("welcome_block"):
            dynamic_block = str(cfg["welcome_block"])
    html = render_welcome_email_html(school, contact_email, dynamic_block=dynamic_block)
    subject = f"Your school is ready — {getattr(school, 'name', 'Your School')}"
    from_email = _regional_from_email(school)
    try:
        msg = EmailMessage(
            subject=subject,
            body=html,
            from_email=from_email,
            to=[contact_email.strip()],
        )
        msg.content_subtype = "html"
        msg.send(fail_silently=False)
        logger.info("Welcome email sent to %s for school %s", contact_email, school_id)
        return True
    except Exception as e:
        logger.warning("Welcome email failed for school %s: %s", school_id, e)
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
