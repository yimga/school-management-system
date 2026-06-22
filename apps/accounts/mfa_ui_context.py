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


def mfa_nudge_context(request):
    """Persistent "set up 2FA" nudge for grace / optional enforcement modes.

    ``RequireMFAMiddleware`` stamps ``request.rmc_mfa_nudge`` when a required
    user is let through under grace/optional mode (instead of a hard wall). This
    surfaces it to the shells, honoring a per-session dismissal so the banner
    can be closed but reappears next session (it is a security prompt).
    """
    nudge = getattr(request, "rmc_mfa_nudge", None)
    if not nudge:
        return {"rmc_mfa_nudge": None}
    try:
        if request.session.get("mfa_banner_dismissed"):
            return {"rmc_mfa_nudge": None}
    except (AttributeError, TypeError):
        pass

    data = dict(nudge)
    try:
        # legacy=1 → the polished enrollment page (not the bare studio wizard).
        data["setup_url"] = reverse("accounts:mfa_setup") + "?legacy=1"
    except MFA_CONTEXT_SOFT_FAILURES:
        data["setup_url"] = ""
    try:
        next_path = getattr(request, "get_full_path", lambda: "")() or ""
        data["dismiss_url"] = reverse("accounts:dismiss_mfa_banner")
        if next_path:
            data["dismiss_url"] += "?next=" + next_path
    except MFA_CONTEXT_SOFT_FAILURES:
        data["dismiss_url"] = ""
    try:
        data["policy_url"] = reverse("portal:mfa_policy")
    except MFA_CONTEXT_SOFT_FAILURES:
        data["policy_url"] = ""
    return {"rmc_mfa_nudge": data}
