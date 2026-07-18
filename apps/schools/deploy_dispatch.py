"""Best-effort, one-time setup-email dispatch invoked from a deploy data migration.

Lets a deploy (Render runs ``migrate`` on release) re-send the "your school is
ready" / owner-setup email to a specific tenant's owners — the same path as
``manage.py resend_owner_setup_email``, which routes an owner who hasn't claimed a
credential into the guided onboarding wizard. Kept in its own module (not inside
the migration) so the logic is importable and unit-tested; the migration is a thin,
test-skipped, fail-soft caller.

Delivery still depends on the platform's transactional mail being configured
(Brevo secrets); when it isn't, ``send_welcome_email`` no-ops and this reports 0
sent. Nothing here ever raises — a deploy must never fail on an email.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: The tenant this deploy dispatch targets. Kept as a constant so it's obvious and
#: greppable; a future dispatch for another school reuses the generic function.
GILEAD_TECH_SLUG = "gilead-tech"


def _active_owner_emails(school) -> list[str]:
    from apps.schools.models import SchoolMembership

    emails: list[str] = []
    seen: set[str] = set()
    rows = (
        SchoolMembership.objects.filter(
            school=school, is_school_owner=True, suspended_at__isnull=True
        )
        .select_related("user")
        .order_by("-is_primary", "user__pk")
    )
    for m in rows:
        email = (getattr(m.user, "email", "") or "").strip()
        if email and email.lower() not in seen:
            seen.add(email.lower())
            emails.append(email)
    return emails


def dispatch_setup_email_for_slug(slug: str) -> dict:
    """Resend the owner-setup email to every ACTIVE owner of the school ``slug``.

    Fail-soft: returns a summary and NEVER raises, so a deploy migration can call
    it without risk. ``{"slug", "found", "recipients", "sent"}``.
    """
    result = {"slug": slug, "found": False, "recipients": 0, "sent": 0}
    try:
        from apps.schools.models import School
        from apps.schools.welcome_email import send_welcome_email

        school = School.objects.filter(slug=slug, is_active=True).first()
        if school is None:
            return result
        result["found"] = True
        emails = _active_owner_emails(school)
        result["recipients"] = len(emails)
        for email in emails:
            try:
                if send_welcome_email(str(school.pk), email):
                    result["sent"] += 1
            except Exception:  # noqa: BLE001 — one bad send must not abort the rest
                logger.warning("deploy_dispatch send failed", exc_info=True)
        logger.info(
            "deploy_dispatch slug=%s recipients=%s sent=%s",
            slug,
            result["recipients"],
            result["sent"],
        )
    except Exception:  # noqa: BLE001 — a deploy must never fail on an email dispatch
        logger.warning("deploy_dispatch failed for slug=%s", slug, exc_info=True)
    return result
