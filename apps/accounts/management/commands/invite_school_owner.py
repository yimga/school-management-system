"""Safely invite an additional school-scoped owner by exact school identity."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Create/refresh and email a mandatory-MFA school-owner invitation. "
        "The school ID and slug must both match."
    )

    def add_arguments(self, parser):
        parser.add_argument("--school-id", required=True)
        parser.add_argument("--slug", required=True)
        parser.add_argument("--email", required=True)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and report the action without changing data or sending email.",
        )

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model

        from apps.accounts.tenant_staff_invites import (
            create_tenant_staff_invite,
            normalize_invite_email,
            send_tenant_staff_invite,
            tenant_staff_invite_accept_url,
        )
        from apps.schools.models import School, SchoolMembership

        school_id = (options["school_id"] or "").strip()
        slug = (options["slug"] or "").strip().lower()
        try:
            email = normalize_invite_email(options["email"])
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        school = School.objects.filter(pk=school_id, slug=slug).first()
        if school is None:
            raise CommandError(
                "No school matched both the supplied ID and slug; nothing changed."
            )
        if not school.is_active:
            raise CommandError(
                f"{school.slug} is not active; repair provisioning before inviting an owner."
            )

        User = get_user_model()
        email_users = list(User.objects.filter(email__iexact=email).order_by("pk")[:2])
        if len(email_users) > 1:
            raise CommandError(
                "More than one user has this email. Resolve the duplicate identity first."
            )
        username_owner = (
            User.objects.filter(username__iexact=email).exclude(email__iexact=email).first()
        )
        if username_owner is not None:
            raise CommandError(
                "The requested email is already another account's username. "
                "Resolve the identity collision first."
            )
        if email_users and SchoolMembership.objects.filter(
            school=school,
            user=email_users[0],
            is_school_owner=True,
            suspended_at__isnull=True,
        ).exists():
            self.stdout.write(
                self.style.SUCCESS(
                    f"{email} is already an active owner of {school.slug}; no invite created."
                )
            )
            return

        action = (
            f"invite {email} as school owner of {school.slug} "
            f"({school.pk}); username will be {email}"
        )
        if options["dry_run"]:
            self.stdout.write(f"Dry run: would {action}.")
            return

        invite, created = create_tenant_staff_invite(
            school=school,
            email=email,
            role="ADMIN",
            is_school_owner=True,
        )
        accept_url = tenant_staff_invite_accept_url(invite)
        delivered = send_tenant_staff_invite(invite, accept_url=accept_url)
        state = "created" if created else "refreshed"
        self.stdout.write(
            self.style.SUCCESS(
                f"Owner invite {state} for {email}; expires {invite.expires_at.isoformat()}."
            )
        )
        if delivered:
            self.stdout.write(self.style.SUCCESS("Invitation delivered or queued."))
        else:
            raise CommandError(
                "Invitation was saved but transactional email was not delivered "
                "or queued. Repair email delivery and rerun this idempotent "
                "command; the secret invitation URL was not printed."
            )
