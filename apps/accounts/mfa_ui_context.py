"""Shared MFA UI context for manager operator surfaces (header icon + profile)."""

from __future__ import annotations

from django.urls import NoReverseMatch, reverse

MFA_CONTEXT_SOFT_FAILURES = (
    ImportError,
    AttributeError,
    TypeError,
    NoReverseMatch,
)


def build_mfa_ui_context(request) -> dict:
    """Header icon + profile links; no full-width encourage banners on manager."""
    ctx = {
        "mfa_enrolled": False,
        "mfa_setup_needed": False,
        "show_mfa_header_icon": False,
        "show_mfa_banner": False,
        "mfa_setup_url": "",
        "mfa_profile_url": "",
    }
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return ctx
    if not getattr(user, "is_staff", False):
        return ctx
    if getattr(request, "public_host_kind", None) != "manager":
        return ctx

    ctx["show_mfa_header_icon"] = True
    try:
        ctx["mfa_setup_url"] = reverse("accounts:mfa_setup")
        ctx["mfa_profile_url"] = reverse("accounts:user_profile") + "#mfa-security"
    except MFA_CONTEXT_SOFT_FAILURES:
        return ctx

    try:
        from django_otp import user_has_device

        enrolled = bool(user_has_device(user))
        ctx["mfa_enrolled"] = enrolled
        ctx["mfa_setup_needed"] = not enrolled
        ctx["show_mfa_banner"] = False
    except MFA_CONTEXT_SOFT_FAILURES:
        pass
    return ctx


def operator_mfa_context(request):
    return build_mfa_ui_context(request)
