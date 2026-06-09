"""Absolute URLs for post-provisioning operator emails (no request object)."""

from __future__ import annotations

from django.contrib.auth.tokens import default_token_generator
from django.urls import NoReverseMatch, reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.schools.host_routing import get_canonical_base_domain


def build_public_site_url(path: str) -> str:
    """HTTPS URL on the public marketing host (runmycampus.com).

    Use for signup/onboarding mail links: the signed token is the auth, and the
    wizard is allowlisted on the public urlconf. Tenant subdomains often are not
    DNS-routed yet (or ``is_active`` is still flipping) when the welcome email
    lands — subdomain links bounce to ``/school-not-found/``.
    """
    path = path if path.startswith("/") else f"/{path}"
    try:
        from django.conf import settings

        configured = (getattr(settings, "RMC_PUBLIC_SITE_URL", "") or "").strip()
    except Exception:
        configured = ""
    if configured:
        base = configured.rstrip("/")
        if not base.startswith(("http://", "https://")):
            base = f"https://{base.lstrip('/')}"
    else:
        domain = (get_canonical_base_domain() or "runmycampus.com").strip().lower()
        base = f"https://{domain}"
    return f"{base}{path}"


def build_public_login_url() -> str:
    return build_public_site_url("/authentication/login/")


def tenant_subdomain_host_exists(school) -> bool:
    """True when the school has a slug/subdomain that maps to a tenant host."""
    if not school:
        return False
    token = (
        (getattr(school, "subdomain", None) or getattr(school, "slug", None) or "")
        .strip()
        .lower()
    )
    return bool(token)


def school_subdomain_redirect_is_safe(school) -> bool:
    """True when the tenant subdomain is live (``is_active``) for backend/dashboard."""
    return bool(school and getattr(school, "is_active", False))


def build_tenant_workspace_login_url(school, path: str = "/authentication/login/") -> str:
    """Canonical tenant-host sign-in URL (active or pending provisioning)."""
    return build_tenant_authentication_url(school, path)


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


def build_provision_setup_password_url(school, user, next_path: str = "") -> str:
    """
    One-time password setup link (reuses accounts:legacy_setup token flow).

    The signed token is the auth, so the link works across the public→tenant
    host boundary where a session cookie would not. ``next_path`` (a same-host
    path) is carried through so the user lands on the dashboard after choosing
    a password instead of the bare login page.
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    try:
        path = reverse("accounts:legacy_setup", kwargs={"uidb64": uid, "token": token})
    except NoReverseMatch:
        return ""
    # Post-provision password setup is part of first-run onboarding — public host.
    url = build_public_site_url(path)
    if next_path:
        from urllib.parse import urlencode

        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urlencode({'next': next_path})}"
    return url


def build_owner_onboarding_path(user) -> str:
    """RELATIVE onboarding path (no host) for an in-request redirect.

    Use this for the immediate post-verify redirect so the wizard stays on the
    host the verify link was on (the public site, which ALWAYS resolves).
    ``build_owner_onboarding_url`` (absolute, for mail) targets the same public
    host — tenant subdomains are not safe for first-run mail deep links.
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    try:
        return reverse(
            "accounts:owner_onboarding_account",
            kwargs={"uidb64": uid, "token": token},
        )
    except NoReverseMatch:
        return ""


def build_owner_onboarding_url(school, user) -> str:
    """One-time ABSOLUTE link into the guided first-run onboarding wizard.

    Reuses the password-reset-confirm token, so the signed link is the auth.
    Always targets the **public** site host (same as the verify-signup link):
    tenant subdomains are frequently unrouted on PaaS until wildcard DNS is
    wired, and middleware rejects inactive tenants — both yield
    ``/school-not-found/?slug=…`` and kill first-run UX. For in-request
    redirects, ``build_owner_onboarding_path`` (relative) is equivalent.
    """
    del school  # onboarding auth is token-based; host is always public
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    try:
        path = reverse(
            "accounts:owner_onboarding_account",
            kwargs={"uidb64": uid, "token": token},
        )
    except NoReverseMatch:
        return ""
    return build_public_site_url(path)
