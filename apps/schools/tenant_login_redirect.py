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
