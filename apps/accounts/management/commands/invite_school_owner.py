"""Safely invite an additional school-scoped owner by exact school identity."""

from __future__ import annotations

import os
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


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
            "--confirm-production",
            required=True,
            metavar="SCHOOL_SLUG",
            help="Fail-closed production acknowledgement; must equal --slug.",
        )
        parser.add_argument(
            "--confirm-hostname",
            required=True,
            help="Expected tenant hostname, for example gilead-tech.runmycampus.com.",
        )
        parser.add_argument(
            "--confirm-database",
            required=True,
            help=(
                "Exact active Django database NAME. It is compared but never "
                "printed, preventing an accidental write to another database."
            ),
        )
        parser.add_argument(
            "--expected-revision",
            required=True,
            help="Exact deployed RENDER_GIT_COMMIT that was approved for the invite.",
        )
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
        from apps.accounts.models import TenantStaffInvite
        from apps.schools.models import School, SchoolMembership

        school_id = (options["school_id"] or "").strip()
        slug = (options["slug"] or "").strip().lower()
        self._verify_production_context(options, slug=slug)
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

        expected_hostname = (
            f"{school.subdomain or school.slug}."
            f"{settings.MULTI_TENANT_BASE_DOMAIN}"
        ).strip(".").lower()
        confirmed_hostname = (options["confirm_hostname"] or "").strip().lower()
        if confirmed_hostname != expected_hostname:
            raise CommandError(
                "The confirmed hostname does not match the active school's "
                "canonical tenant hostname; nothing changed."
            )

        from apps.schoolops.email_delivery import transactional_email_configured

        if not transactional_email_configured(school=school):
            raise CommandError(
                "Transactional email is not configured for this school; "
                "nothing changed."
            )

        User = get_user_model()
        email_users = list(User.objects.filter(email__iexact=email).order_by("pk")[:2])
        if len(email_users) > 1:
            raise CommandError(
                "More than one user has this email. Resolve the duplicate identity first."
            )
        if email_users and email_users[0].username.lower() != email:
            raise CommandError(
                "The requested email belongs to an account with a different "
                "username. Resolve the identity collision first."
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
        if (urlparse(accept_url).hostname or "").lower() != expected_hostname:
            raise CommandError(
                "The generated invitation URL did not resolve to the confirmed "
                "tenant hostname. The pending invite was not sent."
            )
        delivered = send_tenant_staff_invite(invite, accept_url=accept_url)
        state = "created" if created else "refreshed"
        self.stdout.write(
            self.style.SUCCESS(
                f"Owner invite {state} for {email}; expires {invite.expires_at.isoformat()}."
            )
        )
        if delivered:
            pending_count = TenantStaffInvite.objects.filter(
                school=school,
                email__iexact=email,
                is_school_owner=True,
                accepted_at__isnull=True,
                expires_at__gt=timezone.now(),
            ).count()
            if pending_count != 1:
                raise CommandError(
                    "Invitation delivery was accepted, but the durable pending "
                    "owner-invite count is not exactly one. Escalate before retrying."
                )
            self.stdout.write(
                self.style.SUCCESS(
                    "Invitation delivered or queued; exactly one pending, "
                    "unexpired owner invite is recorded."
                )
            )
        else:
            raise CommandError(
                "Invitation was saved but transactional email was not delivered "
                "or queued. Repair email delivery and rerun this idempotent "
                "command; the secret invitation URL was not printed."
            )

    @staticmethod
    def _verify_production_context(options, *, slug: str) -> None:
        environment = (
            os.getenv("RMC_ENVIRONMENT") or os.getenv("DJANGO_ENV") or ""
        ).strip().lower()
        if environment not in {"production", "prod"}:
            raise CommandError(
                "invite_school_owner is production-guarded; RMC_ENVIRONMENT "
                "must explicitly identify production."
            )
        if os.getenv("RENDER", "").strip().lower() != "true":
            raise CommandError(
                "invite_school_owner must run inside the active Render service."
            )
        if (options["confirm_production"] or "").strip().lower() != slug:
            raise CommandError(
                "--confirm-production must exactly match --slug; nothing changed."
            )

        current_revision = os.getenv("RENDER_GIT_COMMIT", "").strip().lower()
        expected_revision = (options["expected_revision"] or "").strip().lower()
        if not current_revision or current_revision != expected_revision:
            raise CommandError(
                "The active deployed revision does not match --expected-revision."
            )

        active_database = str(connection.settings_dict.get("NAME") or "")
        if str(options["confirm_database"] or "") != active_database:
            raise CommandError(
                "The active database does not match --confirm-database; nothing changed."
            )

        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            raise CommandError(
                "Unapplied migrations remain in the active database; nothing changed."
            )
