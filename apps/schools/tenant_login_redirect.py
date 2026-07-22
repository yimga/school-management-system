"""Post-login tenant selection for public-host sign-in."""

from __future__ import annotations

from django.urls import reverse


def resolve_post_login_tenant_membership(user, request):
    """
    Pick the school membership to use when redirecting from the public host.

    Prefers the school the owner just verified (``signup_school_id`` session key),
    then an explicit session ``school_id``, then sole membership. When multiple
    active memberships exist and no preference is set, returns ``None`` so the
    caller can send the user to the school picker.
    """
    from apps.schools.models import SchoolMembership
    from apps.schools.provision_email_urls import school_subdomain_redirect_is_safe

    # tenant-isolation-allow: login-flow-post-auth-tenant-membership-resolution-user-scoped
    qs = (
        SchoolMembership.objects.filter(user=user)
        .select_related("school")
        .order_by("-is_primary", "school__name")
    )
    memberships = list(qs)
    if not memberships:
        return None

    preferred_ids: list[str] = []
    signup_id = (request.session.pop("signup_school_id", None) or "").strip()
    if signup_id:
        preferred_ids.append(signup_id)
    session_id = (request.session.get("school_id") or "").strip()
    if session_id and session_id not in preferred_ids:
        preferred_ids.append(session_id)

    for school_id in preferred_ids:
        for membership in memberships:
            if str(membership.school_id) == school_id:
                return membership

    active = [
        m
        for m in memberships
        if m.school and school_subdomain_redirect_is_safe(m.school)
    ]
    if len(active) > 1:
        return None
    if len(active) == 1:
        return active[0]

    pending = [m for m in memberships if m.school and not m.school.is_active]
    if len(pending) == 1:
        return pending[0]
    if len(memberships) == 1:
        return memberships[0]
    return None


def redirect_to_school_picker(request, *, next_name: str = "accounts:redirect"):
    from django.shortcuts import redirect

    try:
        next_path = reverse(next_name)
    except Exception:
        next_path = "/authentication/redirect/"
    return redirect(f"{reverse('accounts:school_picker')}?next={next_path}")


def build_public_handoff_to_tenant_workspace(request, school) -> str | None:
    """
    After public-host sign-in, send the user to their slug URL.

    Session cookies on ``.runmycampus.com`` carry across hosts so the tenant
    login page can finish routing (dashboard, onboarding, or picker).
    """
    if not school:
        return None
    from urllib.parse import urlencode

    from apps.schools.provision_email_urls import (
        build_tenant_authentication_url,
        school_subdomain_redirect_is_safe,
        tenant_subdomain_host_exists,
    )
    from apps.schools.tenant_url import build_tenant_backend_url

    if not tenant_subdomain_host_exists(school):
        return None
    if school_subdomain_redirect_is_safe(school):
        return build_tenant_backend_url(request, school)
    # Portal not fully live yet — never dump an already-authenticated user back
    # onto the tenant login form (password → redirect → login loop). Prefer MFA
    # when a *confirmed* device exists; never send verify without a device (that
    # looped owners: verify → redirect → login). Otherwise onboarding/redirect.
    try:
        from apps.accounts.middleware import RequireMFAMiddleware
        from apps.accounts.post_login_mfa import _user_has_mfa_device

        user = getattr(request, "user", None)
        if (
            user
            and getattr(user, "is_authenticated", False)
            and _user_has_mfa_device(user)
            and not RequireMFAMiddleware._is_mfa_verified(request)
        ):
            path = "/authentication/mfa/verify/"
            try:
                next_path = reverse("accounts:redirect")
                path = f"{path}?{urlencode({'next': next_path})}"
            except Exception:
                pass
            return build_tenant_authentication_url(school, path)
    except ImportError:
        pass
    try:
        next_path = reverse("accounts:owner_onboarding_done")
    except Exception:
        next_path = "/authentication/onboarding/done/"
    try:
        redirect_path = reverse("accounts:redirect")
    except Exception:
        redirect_path = "/authentication/redirect/"
    # Prefer redirect (will land on provisioning/onboarding) over a fresh login.
    return build_tenant_authentication_url(school, redirect_path or next_path)


def redirect_to_tenant_workspace(request, school):
    """HTTP redirect to the school's workspace host."""
    from django.shortcuts import redirect

    target = build_public_handoff_to_tenant_workspace(request, school)
    if target:
        return redirect(target)
    return redirect_to_school_picker(request)


def resolve_public_post_login_handoff(request, user):
    """
    After sign-in on the public or manager host, route tenant members to their
    slug URL (or school picker when multiple memberships exist).
    """
    from apps.schools.models import SchoolMembership
    from apps.schools.provision_email_urls import school_subdomain_redirect_is_safe
    from apps.schools.tenant_url import build_tenant_backend_url, is_base_domain

    if not getattr(user, "is_authenticated", False):
        return None
    try:
        host_ok = is_base_domain(request) or (
            getattr(request, "public_host_kind", None) == "manager"
        )
        if not host_ok:
            try:
                from apps.schools.host_routing import public_host_kind

                host = (request.get_host() or "").split(":")[0].lower()
                host_ok = public_host_kind(host) == "manager"
            except (ImportError, AttributeError, TypeError, ValueError):
                host_ok = False
        if not host_ok:
            return None
    except (AttributeError, ImportError, TypeError, ValueError):
        return None

    m = resolve_post_login_tenant_membership(user, request)
    # tenant-isolation-allow: login-flow-multi-tenant-picker-routing-user-scoped
    if m is None and SchoolMembership.objects.filter(user=user).count() > 1:
        return redirect_to_school_picker(request)
    if m and m.school:
        if school_subdomain_redirect_is_safe(m.school):
            from django.shortcuts import redirect

            return redirect(build_tenant_backend_url(request, m.school))
        return redirect_to_tenant_workspace(request, m.school)
    return None
