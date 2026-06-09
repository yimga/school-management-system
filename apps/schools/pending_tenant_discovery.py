"""Resolve inactive / in-provisioning schools for public discovery surfaces.

Self-service signup creates ``School`` rows with ``is_active=False`` until
provisioning finishes. Public finders and tenant middleware only matched
``is_active=True``, so owners saw ``/school-not-found/?slug=…`` even though
the school existed.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from django.db.models import Q
from django.urls import NoReverseMatch, reverse
from django.utils.text import slugify

from apps.schools.provision_email_urls import (
    build_owner_onboarding_url,
    build_public_login_url,
    build_public_site_url,
    build_tenant_authentication_url,
)

logger = logging.getLogger(__name__)


def normalize_slug_token(raw: str) -> str:
    return slugify((raw or "").strip())[:120]


def list_active_schools_for_public_login(*, limit: int = 250) -> list[dict[str, str]]:
    """Active tenant rows for the public login school picker (name + slug)."""
    from apps.schools.models import School

    rows: list[dict[str, str]] = []
    qs = (
        School.objects.filter(is_active=True)
        .order_by("name")
        .only("name", "slug", "subdomain")[:limit]
    )
    for school in qs:
        token = (
            (getattr(school, "subdomain", None) or getattr(school, "slug", None) or "")
            .strip()
            .lower()
        )
        if not token:
            continue
        rows.append(
            {
                "name": (school.name or token).strip(),
                "slug": token,
            }
        )
    return rows


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


def owner_needs_account_setup(school) -> bool:
    """True when the owner still must set a password (not post-verify provisioning)."""
    state = pending_school_state(school)
    if state != "provisioning":
        return False
    owner = _primary_owner_user(school)
    if owner is None:
        return False
    return not owner.has_usable_password()


def _provisioning_job_in_flight(school) -> bool:
    """True when a provision job started recently and has not failed."""
    if school is None:
        return False
    try:
        from apps.schools.provisioning_progress import _latest_workflow_run

        run = _latest_workflow_run(school)
        if run is not None:
            status = (getattr(run, "status", "") or "").strip().lower()
            return status in ("running", "")
    except ImportError:
        run = None
    try:
        from apps.schools.models import SchoolProvisioningEvent

        started = (
            SchoolProvisioningEvent.objects.filter(
                school=school,
                event_type="STARTED",
            )
            .order_by("-created_at")
            .first()
        )
        if not started or not getattr(started, "created_at", None):
            return False
        failed = (
            SchoolProvisioningEvent.objects.filter(
                school=school,
                event_type="FAILED",
                created_at__gte=started.created_at,
            )
            .exists()
        )
        return not failed
    except (ImportError, AttributeError, TypeError, ValueError):
        return False


def kick_pending_tenant_provisioning(request, school, *, force: bool = False) -> bool:
    """
    Queue + sync provisioning for anonymous tenant setup surfaces.

    Mirrors ``_kick_provisioning_on_done_page`` but works without a logged-in
    owner session (uses primary owner email for the provision job).
    """
    if not school or getattr(school, "is_active", False):
        return False
    try:
        from apps.schools.provisioning_progress import resolve_portal_ready

        if resolve_portal_ready(school):
            return False
    except ImportError:
        pass

    if not force and _provisioning_job_in_flight(school):
        return False

    session_key = f"pending_provision_kick:{school.pk}"
    now_ts = time.time()
    cooldown = 30  # magic-number-allow: pending-provision-kick-cooldown-seconds
    if (
        not force
        and request is not None
        and getattr(request, "session", None) is not None
    ):
        last_ts = request.session.get(session_key)
        if last_ts and (now_ts - float(last_ts)) < cooldown:
            return False
        request.session[session_key] = now_ts

    owner = _primary_owner_user(school)
    contact_email = (getattr(owner, "email", "") or "").strip()
    try:
        from apps.schools.tasks import kick_complete_provisioning_background

        kick_complete_provisioning_background(
            str(school.pk), contact_email=contact_email
        )
        logger.info(
            "pending_tenant_provision_kick_queued school_id=%s",
            getattr(school, "pk", None),
        )
        return True
    except Exception:  # noqa: BLE001 - provisioning kick must never break the page
        logger.warning("pending_tenant_provision_kick_failed", exc_info=True)
        return False


def build_pending_recovery_links(school) -> dict[str, str]:
    """Recovery URLs for owners stuck before ``is_active=True``."""
    links: dict[str, str] = {}
    state = pending_school_state(school)

    try:
        from apps.schools.provisioning_progress import resolve_portal_ready

        portal_ready = resolve_portal_ready(school)
    except ImportError:
        portal_ready = bool(getattr(school, "is_active", False))

    if portal_ready:
        links["login_url"] = build_tenant_authentication_url(
            school, "/authentication/login/"
        )

    if state == "awaiting_verification":
        try:
            links["resend_verification_url"] = build_public_site_url(
                reverse("resend_signup_verification")
            )
        except NoReverseMatch:
            links["resend_verification_url"] = build_public_site_url(
                "/verify-signup/resend/"
            )

    if owner_needs_account_setup(school):
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
    owner = _primary_owner_user(school)
    progress: dict[str, Any] = {}
    portal_ready = False
    try:
        from apps.schools.provisioning_progress import resolve_provisioning_progress

        progress = resolve_provisioning_progress(school)
        portal_ready = bool(progress.get("portal_ready"))
    except ImportError:
        portal_ready = bool(getattr(school, "is_active", False))

    return {
        "pending_school": school,
        "pending_state": state,
        "pending_recovery_links": links,
        "pending_school_name": (school.name or school.slug or "").strip(),
        "portal_ready": portal_ready,
        "provision_initial_steps": progress.get("steps") or [],
        "provision_progress_percent": progress.get("progress_percent", 0),
        "provision_current_step_label": progress.get("current_step_label") or "",
        "owner_email": (getattr(owner, "email", "") or "") if owner else "",
        "tenant_blank_brand": True,
    }


def _portal_url_for_school(request, school) -> str:
    from apps.schools.provision_email_urls import (
        build_public_login_url,
        build_tenant_authentication_url,
        school_subdomain_redirect_is_safe,
    )
    from apps.schools.section8_views import _build_school_portal_url

    state = pending_school_state(school)
    if not state and school_subdomain_redirect_is_safe(school):
        return build_tenant_authentication_url(school, "/authentication/login/")
    if state:
        if state == "awaiting_verification":
            try:
                return build_public_site_url(reverse("resend_signup_verification"))
            except NoReverseMatch:
                return build_public_site_url("/verify-signup/resend/")
        from apps.schools.provision_email_urls import (
            build_tenant_authentication_url,
            tenant_subdomain_host_exists,
        )

        if tenant_subdomain_host_exists(school):
            return build_tenant_authentication_url(school, "/")
        owner = _primary_owner_user(school)
        if owner is not None:
            onboarding = build_owner_onboarding_url(school, owner)
            if onboarding:
                return onboarding
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
