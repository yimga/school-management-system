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


def _active_owner_emails(school, *, user_ids=None) -> list[str]:
    from apps.schools.models import SchoolMembership

    emails: list[str] = []
    seen: set[str] = set()
    rows = SchoolMembership.objects.filter(
        school=school, is_school_owner=True, suspended_at__isnull=True
    ).select_related("user")
    if user_ids:
        rows = rows.filter(user_id__in=list(user_ids))
    rows = rows.order_by("-is_primary", "user__pk")
    for m in rows:
        email = (getattr(m.user, "email", "") or "").strip()
        if email and email.lower() not in seen:
            seen.add(email.lower())
            emails.append(email)
    return emails


def dispatch_setup_email_for_school(school, *, owner_user_ids=None) -> dict:
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

        emails = _active_owner_emails(school, user_ids=owner_user_ids)
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


def _addressable_members(school, *, user_ids=None):
    """``(user, is_owner)`` for NON-SUSPENDED members of ``school``, owners first.

    The recipient resolver for the operator "resend setup email" action. When
    ``user_ids`` is given it restricts to those members — but ALWAYS via this
    school's membership rows, so an id that is not a member of this school (or
    belongs to another tenant) is silently dropped and can never trigger mail.
    When ``user_ids`` is falsy it defaults to the school's OWNERS (preserving the
    original owner-only behaviour when the operator selects nothing). De-dupes by
    user pk and skips members with neither an email nor a username (nothing to
    send to).
    """
    from apps.schools.models import SchoolMembership

    rows = SchoolMembership.objects.filter(
        school=school, suspended_at__isnull=True
    ).select_related("user")
    if user_ids:
        rows = rows.filter(user_id__in=list(user_ids))
    else:
        rows = rows.filter(is_school_owner=True)
    rows = rows.order_by("-is_school_owner", "-is_primary", "user__pk")

    members: list = []
    seen: set = set()
    for m in rows:
        user = getattr(m, "user", None)
        pk = getattr(user, "pk", None)
        if user is None or pk is None or pk in seen:
            continue
        identifier = (getattr(user, "email", "") or "").strip() or (
            getattr(user, "username", "") or ""
        ).strip()
        if not identifier:
            continue
        seen.add(pk)
        members.append((user, bool(m.is_school_owner)))
    return members


def dispatch_setup_email_for_users(school, *, user_ids=None, request=None) -> dict:
    """Resend the account setup / claim email to SELECTED members of a school.

    The operator-console generalization of :func:`dispatch_setup_email_for_school`:
    the operator picks specific tenant users — owners AND non-owner staff, or any
    member targeted by email — instead of blasting every owner. Each recipient is
    routed to the RIGHT email:

    * an OWNER gets the "your school is ready" welcome (the owner onboarding
      wizard link) — identical to the owner-only path;
    * a NON-OWNER gets the generic set-password / claim link (the same audited
      password-reset-confirm link the login recovery uses), because routing a
      teacher / parent into the *owner* onboarding wizard would be wrong.

    Recipients are ALWAYS re-resolved from this school's memberships (see
    :func:`_addressable_members`), so a ``user_ids`` list that references a
    non-member — or another tenant's user — can never trigger mail: the operator
    cannot address outside the school. Fail-soft; never raises. Returns the same
    shape as :func:`dispatch_setup_email_for_school`
    (``{"found", "recipients", "sent", "configured"}``).
    """
    result = {"found": False, "recipients": 0, "sent": 0, "configured": None}
    if school is None:
        return result
    result["found"] = True
    try:
        # Honest preflight — same signal the owner path + CLI surface.
        try:
            from apps.schoolops.email_delivery import transactional_email_configured

            result["configured"] = bool(transactional_email_configured(school=school))
        except Exception:  # noqa: BLE001 — preflight is advisory, never fatal
            result["configured"] = None
        if result["configured"] is False:
            logger.warning(
                "dispatch_setup_email_for_users: transactional email is NOT "
                "configured (Brevo EMAIL_HOST_USER / EMAIL_HOST_PASSWORD empty) — "
                "the setup email for school=%s will be attempted but not delivered "
                "until those secrets are set.",
                getattr(school, "pk", None),
            )

        from apps.accounts.login_recovery import send_set_password_link
        from apps.schools.welcome_email import send_welcome_email

        members = _addressable_members(school, user_ids=user_ids)
        result["recipients"] = len(members)
        for user, is_owner in members:
            try:
                if is_owner:
                    # The owner welcome resolves the account by email address.
                    email = (getattr(user, "email", "") or "").strip()
                    ok = bool(email) and send_welcome_email(str(school.pk), email)
                else:
                    # Non-owners get the generic claim / set-password link, which
                    # works by email OR username and activates a never-claimed
                    # account on claim.
                    ok = send_set_password_link(request, user)
                if ok:
                    result["sent"] += 1
            except Exception:  # noqa: BLE001 — one bad send must not abort the rest
                logger.warning(
                    "dispatch_setup_email_for_users send failed", exc_info=True
                )
        logger.info(
            "dispatch_setup_email_for_users school=%s recipients=%s sent=%s",
            getattr(school, "pk", None),
            result["recipients"],
            result["sent"],
        )
    except Exception:  # noqa: BLE001 — an operator action must never 500 on an email
        logger.warning(
            "dispatch_setup_email_for_users failed for school=%s",
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

        # The slug/deploy path has no per-user selection — resend to every active
        # owner. (A stray ``user_ids=owner_user_ids`` here referenced an undefined
        # name, so this whole path raised NameError and silently sent nothing.)
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
