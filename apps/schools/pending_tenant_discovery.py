"""Resolve inactive / in-provisioning schools for public discovery surfaces.

Self-service signup creates ``School`` rows with ``is_active=False`` until
provisioning finishes. Public finders and tenant middleware only matched
``is_active=True``, so owners saw ``/school-not-found/?slug=…`` even though
the school existed.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Q
from django.urls import NoReverseMatch, reverse
from django.utils.text import slugify

from apps.schools.provision_email_urls import (
    build_owner_onboarding_url,
    build_public_login_url,
    build_public_site_url,
)


def normalize_slug_token(raw: str) -> str:
    return slugify((raw or "").strip())[:120]


def lookup_school_by_slug_or_subdomain(token: str):
    """Case-insensitive slug or subdomain match, active or inactive."""
    from apps.schools.models import School

    normalized = normalize_slug_token(token)
    if not normalized:
        return None
    return (
        School.objects.filter(
            Q(slug__iexact=normalized) | Q(subdomain__iexact=normalized)
        )
        .order_by("-created_at")
        .first()
    )


def pending_school_state(school) -> str | None:
    """
    Return a pending state code when the school is not yet publicly routable.

    * ``awaiting_verification`` — signup created, email not verified yet
    * ``provisioning`` — verified but ``is_active`` still false
    * ``None`` — school is live (or unknown)
    """
    if not school or getattr(school, "is_active", False):
        return None
    try:
        verification = getattr(school, "signup_verification", None)
    except Exception:
        verification = None
    if verification is not None and verification.verified_at is None:
        return "awaiting_verification"
    return "provisioning"


def _primary_owner_user(school):
    from apps.accounts.models import User
    from apps.schools.models import SchoolMembership

    membership = (
        SchoolMembership.objects.filter(
            school=school,
            is_primary=True,
        )
        .select_related("user")
        .order_by("id")
        .first()
    )
    if membership and membership.user_id:
        return membership.user
    membership = (
        SchoolMembership.objects.filter(
            school=school,
            role=User.Role.ADMIN,
        )
        .select_related("user")
        .order_by("id")
        .first()
    )
    return membership.user if membership else None


def build_pending_recovery_links(school) -> dict[str, str]:
    """Public-host URLs for owners stuck before ``is_active=True``."""
    links: dict[str, str] = {
        "login_url": build_public_login_url(),
    }
    try:
        links["resend_verification_url"] = build_public_site_url(
            reverse("resend_signup_verification")
        )
    except NoReverseMatch:
        links["resend_verification_url"] = build_public_site_url(
            "/verify-signup/resend/"
        )
    try:
        links["onboarding_done_url"] = build_public_site_url(
            reverse("accounts:owner_onboarding_done")
        )
    except NoReverseMatch:
        links["onboarding_done_url"] = build_public_site_url(
            "/authentication/onboarding/done/"
        )
    owner = _primary_owner_user(school)
    if owner is not None:
        onboarding = build_owner_onboarding_url(school, owner)
        if onboarding:
            links["continue_setup_url"] = onboarding
    return links


def pending_school_public_context(school) -> dict[str, Any]:
    state = pending_school_state(school)
    if not state:
        return {}
    links = build_pending_recovery_links(school)
    return {
        "pending_school": school,
        "pending_state": state,
        "pending_recovery_links": links,
        "pending_school_name": (school.name or school.slug or "").strip(),
    }


def _portal_url_for_school(request, school) -> str:
    from apps.schools.section8_views import _build_school_portal_url

    state = pending_school_state(school)
    if state:
        owner = _primary_owner_user(school)
        if owner is not None:
            onboarding = build_owner_onboarding_url(school, owner)
            if onboarding:
                return onboarding
        if state == "awaiting_verification":
            try:
                return build_public_site_url(reverse("resend_signup_verification"))
            except NoReverseMatch:
                return build_public_site_url("/verify-signup/resend/")
        return build_public_login_url()
    return _build_school_portal_url(request, school)


def search_schools_for_public_finder(request, query: str, *, limit: int = 8) -> list[dict]:
    """
    Finder results for marketing + school-not-found surfaces.

    Active schools: name/subdomain partial match.
    Inactive schools: **exact** slug/subdomain match only (avoid leaking names).
    """
    from apps.schools.models import School

    query = (query or "").strip()
    if len(query) < 2:
        return []

    normalized = normalize_slug_token(query)
    results: list[dict] = []
    seen_ids: set = set()

    if normalized:
        pending = (
            School.objects.filter(is_active=False)
            .filter(Q(slug__iexact=normalized) | Q(subdomain__iexact=normalized))
            .order_by("-created_at")[:3]
        )
        for school in pending:
            seen_ids.add(school.pk)
            state = pending_school_state(school)
            results.append(
                {
                    "name": school.name,
                    "slug": school.slug,
                    "subdomain": getattr(school, "subdomain", "") or "",
                    "portal_url": _portal_url_for_school(request, school),
                    "pending": True,
                    "pending_state": state or "provisioning",
                }
            )

    active = (
        School.objects.filter(is_active=True)
        .filter(
            Q(name__icontains=query)
            | Q(slug__icontains=query)
            | Q(subdomain__icontains=query)
        )
        .order_by("name")[:limit]
    )
    for school in active:
        if school.pk in seen_ids:
            continue
        results.append(
            {
                "name": school.name,
                "slug": school.slug,
                "subdomain": getattr(school, "subdomain", "") or "",
                "portal_url": _portal_url_for_school(request, school),
                "pending": False,
                "pending_state": "",
            }
        )
        if len(results) >= limit:
            break
    return results[:limit]
