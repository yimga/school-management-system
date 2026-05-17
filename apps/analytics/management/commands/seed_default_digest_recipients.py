"""Seed RiskDigestRecipient rows from each school's existing admin users.

Discovers users with `role in {ADMIN, PRINCIPAL, PROPRIETOR}` for every
active school and creates an enabled email recipient row per
(school, user.email). Idempotent via the unique constraint on
(school, channel, target) — re-running is safe.

Use this once after migration 0027 lands so operators have something
to send to immediately. They customise via admin afterwards
(add Slack webhooks, disable specific addresses, etc.).
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand
from django.db import IntegrityError

from apps.accounts.models import User
from apps.analytics.models import RiskDigestRecipient
from apps.schools.models import School

logger = logging.getLogger(
    "apps.analytics.commands.seed_default_digest_recipients"
)

_ADMIN_ROLES = {"ADMIN", "PRINCIPAL", "PROPRIETOR"}


class Command(BaseCommand):
    help = "Seed RiskDigestRecipient rows from each school's admin/principal users."

    def add_arguments(self, parser):
        parser.add_argument("--school", default=None, help="Slug; omit for all active.")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Show what would be created; do not write rows.",
        )
        parser.add_argument(
            "--enable", action="store_true",
            help="Mark newly-created rows as enabled (default: disabled, opt-in).",
        )

    def handle(self, *args, **opts):
        schools = School.objects.filter(is_active=True)
        if opts.get("school"):
            schools = schools.filter(slug=opts["school"])
        created = skipped = 0
        for school in schools:
            # tenant-isolation-allow: scoped via school= below
            admins = User.objects.filter(
                school_memberships__school=school,
                school_memberships__role__in=_ADMIN_ROLES,
            ).distinct() if hasattr(User, "school_memberships") else (
                User.objects.filter(role__in=_ADMIN_ROLES)
            )
            for user in admins:
                email = (getattr(user, "email", "") or "").strip()
                if not email:
                    continue
                if opts.get("dry_run"):
                    self.stdout.write(
                        f"  [dry] {school.slug}: would seed email={email}"
                    )
                    created += 1
                    continue
                try:
                    _, was_created = RiskDigestRecipient.objects.get_or_create(
                        school=school,
                        channel=RiskDigestRecipient.Channel.EMAIL,
                        target=email,
                        defaults={
                            "label": (
                                f"{(getattr(user, 'role', '') or 'admin').lower()} "
                                f"({user.username})"
                            )[:120],
                            "enabled": bool(opts.get("enable")),
                        },
                    )
                except IntegrityError:
                    skipped += 1
                    continue
                if was_created:
                    created += 1
                else:
                    skipped += 1
        verb = "Would create" if opts.get("dry_run") else "Created"
        self.stdout.write(self.style.SUCCESS(
            f"{verb} {created} recipient(s); skipped {skipped} existing/empty."
        ))
