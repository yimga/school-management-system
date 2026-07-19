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


def dispatch_setup_email_for_school(school) -> dict:
    """Resend the owner-setup email to every ACTIVE owner of a resolved ``school``.

    Operator-initiated sibling of :func:`dispatch_setup_email_for_slug`: takes a
    ``School`` the operator already selected (e.g. from the tenant-360 console) and
    does NOT re-filter on ``is_active`` — the operator picked this tenant on
    purpose. Fail-soft; never raises. Returns
    ``{"found", "recipients", "sent", "configured"}`` (``configured`` is the honest
    "can we actually deliver mail right now?" flag: ``True`` / ``False`` / ``None``).
    """
    result = {"found": False, "recipients": 0, "sent": 0, "configured": None}
    if school is None:
        return result
    result["found"] = True
    try:
        from apps.schools.welcome_email import send_welcome_email

        # Honest preflight — same signal the CLI/migration path surfaces.
        try:
            from apps.schoolops.email_delivery import transactional_email_configured

            result["configured"] = bool(transactional_email_configured(school=school))
        except Exception:  # noqa: BLE001 — preflight is advisory, never fatal
            result["configured"] = None
        if result["configured"] is False:
            logger.warning(
                "dispatch_setup_email_for_school: transactional email is NOT "
                "configured (Brevo EMAIL_HOST_USER / EMAIL_HOST_PASSWORD empty) — "
                "the setup email for school=%s will be attempted but not delivered "
                "until those secrets are set.",
                getattr(school, "pk", None),
            )

        emails = _active_owner_emails(school)
        result["recipients"] = len(emails)
        for email in emails:
            try:
                if send_welcome_email(str(school.pk), email):
                    result["sent"] += 1
            except Exception:  # noqa: BLE001 — one bad send must not abort the rest
                logger.warning(
                    "dispatch_setup_email_for_school send failed", exc_info=True
                )
        logger.info(
            "dispatch_setup_email_for_school school=%s recipients=%s sent=%s",
            getattr(school, "pk", None),
            result["recipients"],
            result["sent"],
        )
    except Exception:  # noqa: BLE001 — an operator action must never 500 on an email
        logger.warning(
            "dispatch_setup_email_for_school failed for school=%s",
            getattr(school, "pk", None),
            exc_info=True,
        )
    return result


def dispatch_setup_email_for_slug(slug: str) -> dict:
    """Resend the owner-setup email to every ACTIVE owner of the school ``slug``.

    Fail-soft: returns a summary and NEVER raises, so a deploy migration can call
    it without risk. ``{"slug", "found", "recipients", "sent", "configured"}``.
    ``configured`` is the honest "can this deploy actually deliver mail?" flag
    (``True`` / ``False`` / ``None`` if the preflight couldn't run).
    """
    result = {
        "slug": slug,
        "found": False,
        "recipients": 0,
        "sent": 0,
        "configured": None,
    }
    try:
        from apps.schools.models import School
        from apps.schools.welcome_email import send_welcome_email

        school = School.objects.filter(slug=slug, is_active=True).first()
        if school is None:
            return result
        result["found"] = True

        # Honest preflight: record + loudly log whether transactional mail is
        # actually configured, so a deploy that "ran the dispatch" but delivered
        # nothing (Brevo secrets empty) leaves a clear breadcrumb in the release
        # log instead of a silent 0-sent. Never gates the attempt.
        try:
            from apps.schoolops.email_delivery import transactional_email_configured

            result["configured"] = bool(transactional_email_configured(school=school))
        except Exception:  # noqa: BLE001 — preflight is advisory, never fatal
            result["configured"] = None
        if result["configured"] is False:
            logger.warning(
                "deploy_dispatch: transactional email is NOT configured "
                "(Brevo EMAIL_HOST_USER / EMAIL_HOST_PASSWORD empty) — the "
                "setup email for slug=%s will be attempted but not delivered "
                "until those secrets are set.",
                slug,
            )

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
