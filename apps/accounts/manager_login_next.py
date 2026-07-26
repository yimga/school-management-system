"""Sanitize login ``next`` targets on the manager (control-plane) host.

School owners who bookmark ``manager.runmycampus.com/authentication/login/?next=…``
with tenant-only paths (MFA setup, activation gate, onboarding wizard) loop forever
because those flows belong on the public / tenant hosts, not the operator console.
"""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlencode

from django.db import DatabaseError

# Substrings matched against the decoded ``next`` chain (path + nested next= values).
_MANAGER_TOXIC_NEXT_MARKERS = (
    "/activation/",
    "/authentication/onboarding/",
    "/authentication/mfa/",
    "/authentication/backend/",
    "/t/",
)

# Deep links that legitimately target the control plane after operator sign-in.
_MANAGER_OPERATOR_NEXT_PREFIXES = (
    "/super/",
    "/admin/",
)


def _unwrap_nested_next(raw: str, *, max_depth: int = 5) -> str:
    """Follow ``?next=`` nesting so ``/mfa/setup/?next=/activation/…`` is detected."""
    decoded = unquote((raw or "").strip())
    for _ in range(max_depth):
        if not decoded:
            break
        if "?" not in decoded:
            break
        _path, query = decoded.split("?", 1)
        nested = (parse_qs(query, keep_blank_values=False).get("next") or [""])[0]
        if not nested:
            break
        decoded = unquote(nested)
    return decoded


def is_toxic_login_next_for_manager(raw: str) -> bool:
    """True when ``next`` points at tenant signup/onboarding/MFA/activation paths."""
    if not (raw or "").strip():
        return False
    chain = _unwrap_nested_next(raw).lower()
    return any(marker in chain for marker in _MANAGER_TOXIC_NEXT_MARKERS)


def manager_login_next_is_operator_intent(raw: str) -> bool:
    """True when ``next`` targets control-plane paths (e.g. ``/super/schools/``)."""
    if not (raw or "").strip():
        return False
    chain = _unwrap_nested_next(raw).lower()
    return any(prefix in chain for prefix in _MANAGER_OPERATOR_NEXT_PREFIXES)


def login_next_is_safe_same_host_return(request) -> bool:
    """True when a login GET/POST carries a safe, same-host ``next`` to a protected surface.

    This is the signature of a SESSION-DEATH re-auth: Django's ``redirect_to_login``
    always appends such a ``next`` when a login-required view kicks an expired session
    to the login page, whereas a cold visitor typing the URL has none. On the manager
    host every protected surface is operator-only, so a non-toxic same-host return path
    means the visitor was on the operator console — they must be shown the operator
    login (with ``next`` preserved) and NOT ejected to runmycampus.com/discover/.

    Rejected: empty, toxic tenant-flow targets (MFA/onboarding/activation/``/t/``),
    and any off-site / scheme-bearing / protocol-relative ``next`` (open-redirect safe).
    """
    from django.utils.http import url_has_allowed_host_and_scheme

    raw = (request.GET.get("next") or "").strip()
    if not raw and getattr(request, "method", "") == "POST":
        raw = (request.POST.get("next") or "").strip()
    if not raw:
        return False
    if is_toxic_login_next_for_manager(raw):
        return False
    # Same-host relative path only — never an off-site or protocol-relative target.
    if not raw.startswith("/") or raw.startswith("//"):
        return False
    try:
        host = (request.get_host() or "").split(":")[0]
    except (AttributeError, TypeError, ValueError):
        host = ""
    if not url_has_allowed_host_and_scheme(
        raw, allowed_hosts={host} if host else None
    ):
        return False
    return True


def sanitize_manager_login_next(raw: str) -> str:
    """Drop toxic manager-host ``next`` values; pass through safe relative paths."""
    cleaned = (raw or "").strip()
    if is_toxic_login_next_for_manager(cleaned):
        return ""
    return cleaned


def build_public_post_login_url() -> str:
    """Absolute URL on the public host for tenant staff after a manager-host login."""
    from django.urls import reverse

    from apps.schools.provision_email_urls import build_public_site_url

    return build_public_site_url(reverse("accounts:redirect"))


def build_public_login_redirect_url(request) -> str:
    """Public-host login URL preserving safe query params from a manager GET."""
    from django.urls import reverse

    from apps.schools.provision_email_urls import build_public_site_url

    params: dict[str, str] = {}
    next_raw = sanitize_manager_login_next((request.GET.get("next") or "").strip())
    if next_raw:
        params["next"] = next_raw
    role = (request.GET.get("role") or "").strip().lower()
    if role in ("student", "staff", "parent"):
        params["role"] = role
    path = reverse("global_login_discovery")
    if params:
        path = f"{path}?{urlencode(params)}"
    return build_public_site_url(path)


def should_show_manager_login_surface(request) -> bool:
    """
    The manager host login form is operator-only.

    Unauthenticated school owners must use campus discovery on runmycampus.com.
    Operators may
    use the manager form when ``cp=1`` is present or when ``next`` deep-links to
    ``/super/`` or ``/admin/`` (e.g. after ``redirect_to_login`` from ``/super/``).
    """
    if getattr(request.user, "is_authenticated", False):
        return True
    if (request.GET.get("cp") or "").strip() == "1":
        return True
    next_raw = (request.GET.get("next") or "").strip()
    if next_raw and manager_login_next_is_operator_intent(next_raw):
        return True
    # POST may carry next without repeating it in the query string.
    if request.method == "POST":
        post_next = (request.POST.get("next") or "").strip()
        if post_next and manager_login_next_is_operator_intent(post_next):
            return True
    # Session-death re-auth: any safe, non-toxic same-host return path means the
    # visitor was on an operator surface (the manager host serves nothing else) —
    # render the operator login with `next` preserved instead of ejecting them to
    # campus discovery on runmycampus.com. Cold visitors (no `next`) still fall
    # through to discovery below.
    if login_next_is_safe_same_host_return(request):
        return True
    return False


def use_operator_login_template(request) -> bool:
    """Corporate control-plane login vs tenant immersive role-picker login.

    A TENANT subdomain must NEVER render the operator / control-plane ("Manager")
    login skin — not even for an already-authenticated visitor bounced here by a
    permission gate, and not for a ``next=/super/`` / ``?cp=1`` query. Doing so was
    the second half of the finance-lockout bug: an owner denied by a staff gate was
    redirected to ``/authentication/login/`` and, being authenticated,
    ``should_show_manager_login_surface`` returned True → the tenant subdomain served
    the operator sign-in page. The operator skin belongs only to the manager host
    (checked first) or the base/public host when the visitor explicitly signals
    operator intent (handled by ``should_show_manager_login_surface`` below).
    """
    if getattr(request, "public_host_kind", None) == "manager":
        return True
    if getattr(request, "is_tenant_host", False):
        return False
    # Defense in depth: never one boolean deep. A resolved tenant ``school`` is an independent
    # positive tenant signal, so even if ``is_tenant_host`` were ever unset (e.g. a login-render
    # path that ran before UrlConfSwitcherMiddleware set the marker), the operator skin still
    # cannot leak onto a tenant subdomain "by chance".
    if getattr(request, "school", None) is not None:
        return False
    return should_show_manager_login_surface(request)


def request_is_manager_host(request) -> bool:
    """True when the request targets the control-plane manager host."""
    if getattr(request, "public_host_kind", None) == "manager":
        return True
    try:
        from apps.schools.host_routing import public_host_kind

        host = (request.get_host() or "").split(":")[0].lower()
        return public_host_kind(host) == "manager"
    except (ImportError, AttributeError, TypeError, ValueError):
        return False


def tenant_staff_should_use_public_host(user) -> bool:
    """True for school owners/staff who should not stay on the manager console.

    ``CONTROL_PLANE_OPERATOR_ROLES`` may include ``ADMIN`` for legacy env configs,
    but self-service signup owners are tenant ``ADMIN`` users with a
    ``SchoolMembership`` and no ``PlatformOperatorProfile``.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return False
    try:
        from apps.platform_runtime.models_operator_identity import (
            PlatformOperatorProfile,
        )

        profile = PlatformOperatorProfile.objects.filter(user_id=user.pk).first()
        if profile and profile.status in (
            PlatformOperatorProfile.Status.ACTIVE,
            PlatformOperatorProfile.Status.INVITED,
        ):
            return False
    except (ImportError, AttributeError, DatabaseError, TypeError, ValueError):
        pass
    try:
        from apps.schools.models import SchoolMembership

        # tenant-isolation-allow: login-flow-user-membership-existence-before-tenant-bind
        return SchoolMembership.objects.filter(user=user).exists()
    except (ImportError, AttributeError, DatabaseError, TypeError, ValueError):
        return False
