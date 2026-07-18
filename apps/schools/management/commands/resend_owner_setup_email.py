"""Resend the provisioning "your school is ready" / owner-setup email.

Reuses ``apps/schools/welcome_email.send_welcome_email``, which already routes an
owner who has NOT yet claimed a credential to the guided owner-onboarding wizard
(the profile-setup flow, ``accounts:owner_onboarding_account``) and an owner who
HAS to the tenant sign-in page. So a resend both re-delivers the mail AND lands
the owner in the right next step — no duplicate email logic here.

Recipients default to the school's active owners (``SchoolMembership`` with
``is_school_owner=True`` and not suspended) — i.e. the address each owner used at
signup — so this works for the multi-owner case too. ``--email`` targets one
address; ``--dry-run`` previews without sending.

Delivery still depends on the platform's transactional mail being configured
(Brevo ``EMAIL_HOST_USER`` / ``EMAIL_HOST_PASSWORD``); when it isn't, the send
layer no-ops and this reports ``skipped`` rather than failing.

Usage::

    python manage.py resend_owner_setup_email --school gilead-tech
    python manage.py resend_owner_setup_email --school gilead-tech --email owner@example.com
    python manage.py resend_owner_setup_email --school gilead-tech --dry-run
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Resend the owner setup / 'school is ready' email for a school."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            dest="school",
            required=True,
            help="School slug (or numeric/UUID id) to resend for.",
        )
        parser.add_argument(
            "--email",
            dest="email",
            default="",
            help="Send to this one address instead of every active owner.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show who would receive the email without sending anything.",
        )

    def _resolve_school(self, ident: str):
        from django.core.exceptions import ValidationError

        from apps.schools.models import School

        ident = (ident or "").strip()
        school = School.objects.filter(slug=ident).first()
        if school is None:
            # Fall back to pk (int or UUID string) so operators can pass either;
            # a non-slug that is also not a valid pk (School.pk is a UUID) must
            # resolve to "not found", not raise.
            try:
                school = School.objects.filter(pk=ident).first()
            except (ValidationError, ValueError, TypeError):
                school = None
        return school

    def _owner_emails(self, school) -> list[str]:
        """Distinct, non-empty emails of the school's ACTIVE owners, in a stable order."""
        from apps.schools.models import SchoolMembership

        rows = (
            SchoolMembership.objects.filter(
                school=school, is_school_owner=True, suspended_at__isnull=True
            )
            .select_related("user")
            .order_by("-is_primary", "user__pk")
        )
        seen: set[str] = set()
        emails: list[str] = []
        for m in rows:
            email = (getattr(m.user, "email", "") or "").strip()
            key = email.lower()
            if email and key not in seen:
                seen.add(key)
                emails.append(email)
        return emails

    def handle(self, *args, **options):
        school = self._resolve_school(options["school"])
        if school is None:
            raise CommandError(f"No school found for '{options['school']}'.")

        one = (options.get("email") or "").strip()
        recipients = [one] if one else self._owner_emails(school)
        dry_run = bool(options.get("dry_run"))

        label = f"{school.slug or school.pk} ({getattr(school, 'name', '')})"
        if not recipients:
            self.stdout.write(
                self.style.WARNING(
                    f"{label}: no active owner with an email address. "
                    f"Run `audit_school_owners --repair` or pass --email."
                )
            )
            return

        self.stdout.write(f"{label}: {len(recipients)} recipient(s).")

        # Honest preflight: if the platform's transactional mail isn't wired up
        # (Brevo secrets empty), say so LOUDLY up front — otherwise every row
        # below reads as a bland "skipped" and the operator is left guessing why
        # nothing arrived. Advisory only; the send itself stays authoritative.
        mail_ready = True
        try:
            from apps.schoolops.email_delivery import transactional_email_configured

            mail_ready = transactional_email_configured(school=school)
        except Exception:  # noqa: BLE001 — a preflight must never abort the command
            mail_ready = True
        if not dry_run and not mail_ready:
            self.stdout.write(
                self.style.WARNING(
                    "  Transactional email is NOT configured "
                    "(Brevo EMAIL_HOST_USER / EMAIL_HOST_PASSWORD are empty). "
                    "Sends below will be attempted and audited but will NOT be "
                    "delivered until those two secrets are set in the environment."
                )
            )

        from apps.schools.welcome_email import send_welcome_email

        sent = 0
        for email in recipients:
            if dry_run:
                self.stdout.write(f"  would send -> {email}")
                continue
            ok = send_welcome_email(str(school.pk), email)
            if ok:
                sent += 1
                self.stdout.write(self.style.SUCCESS(f"  sent/queued -> {email}"))
                logger.info(
                    "resend_owner_setup_email.sent school=%s", getattr(school, "pk", None)
                )
            else:
                reason = (
                    "email not configured — set Brevo EMAIL_HOST_USER / EMAIL_HOST_PASSWORD"
                    if not mail_ready
                    else "send failed, or no matching owner account"
                )
                self.stdout.write(
                    self.style.WARNING(f"  skipped -> {email} ({reason})")
                )

        if dry_run:
            self.stdout.write("Dry run — nothing sent.")
        else:
            self.stdout.write(self.style.SUCCESS(f"Done: {sent}/{len(recipients)} delivered/queued."))
