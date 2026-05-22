"""Absolute URLs for post-provisioning operator emails (no request object)."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.urls import NoReverseMatch, reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.schools.host_routing import get_canonical_base_domain


def build_tenant_authentication_url(school, path: str) -> str:
    """HTTPS URL on the school subdomain (or verified custom domain)."""
    path = path if path.startswith("/") else f"/{path}"
    # Transactional mail links must be HTTPS for operators (even in DEBUG deploys).
    scheme = "https"
    base_domain = (get_canonical_base_domain() or "").strip().lower()
    if getattr(school, "custom_domain", None) and getattr(
        school, "custom_domain_verified", False
    ):
        host = str(school.custom_domain).strip().lower()
    else:
        sub = (
            (getattr(school, "subdomain", None) or getattr(school, "slug", None) or "")
            .strip()
            .lower()
        )
        host = f"{sub}.{base_domain}" if sub and base_domain else base_domain or "localhost"
    return f"{scheme}://{host}{path}"


def build_provision_setup_password_url(school, user) -> str:
    """
    One-time password setup link (reuses accounts:legacy_setup token flow).
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    try:
        path = reverse("accounts:legacy_setup", kwargs={"uidb64": uid, "token": token})
    except NoReverseMatch:
        return ""
    return build_tenant_authentication_url(school, path)
