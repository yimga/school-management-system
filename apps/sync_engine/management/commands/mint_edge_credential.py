"""Mint an edge machine credential for a sovereign box (operator side, Tier 3 Slice 3).

The operator runs this to issue a per-box bearer credential the edge deployment uses
to authenticate its outbound sync POST. The raw token is printed ONCE (only its sha256
is stored); the box keeps it (e.g. in RMC_EDGE_CREDENTIAL). Revoke by clearing the
device via portal device governance (sets DeviceRegistration.revoked_at).

The credential is bound to a SERVICE USER that must be able to operate on the school
(a school admin/staff member) -- the operator's upstream apply runs AS that user, so
its permissions gate what the sync can write.

    python manage.py mint_edge_credential --slug gilead-tech --user gilead_admin --days 365
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Mint a per-box edge machine credential (bearer token) for edge->operator sync."

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="", help="School slug.")
        parser.add_argument("--school-id", dest="school_id", default="", help="School UUID (alternative to --slug).")
        parser.add_argument("--user", required=True, help="Username of the service user the box acts as (a school admin/staff member).")
        parser.add_argument("--device-id", dest="device_id", default="", help="Stable id for the box (default: edge-<slug>).")
        parser.add_argument("--days", type=int, default=365, help="Credential lifetime in days (default 365).")

    def handle(self, *args, **options):
        from apps.schools.models import School, SchoolMembership
        from apps.sync_engine.edge_outbox import mint_edge_credential

        slug = (options.get("slug") or "").strip()
        school_id = (options.get("school_id") or "").strip()
        if not slug and not school_id:
            raise CommandError("Provide --slug or --school-id.")
        school = (
            School.objects.filter(slug=slug).first()
            if slug
            else School.objects.filter(pk=school_id).first()
        )
        if school is None:
            raise CommandError(f"School not found ({slug or school_id}).")

        username = (options.get("user") or "").strip()
        user = get_user_model().objects.filter(username=username).first()
        if user is None:
            raise CommandError(f"User not found: {username!r}.")

        # The operator's apply runs AS this user, so it must be able to operate on the
        # school. Warn (don't hard-fail) if the binding looks too weak — a superuser or
        # staff member bypasses membership, an ordinary user needs a SchoolMembership.
        has_membership = SchoolMembership.objects.filter(user=user, school=school).exists()
        if not (user.is_superuser or user.is_staff or has_membership):
            self.stderr.write(self.style.WARNING(
                f"WARNING: {username} has no SchoolMembership on {school.slug} and is not "
                "staff/superuser — the sync POST will be rejected by user_may_operate_on_school. "
                "Bind the credential to an admin of this school."
            ))

        try:
            raw_token, token = mint_edge_credential(
                school, user, device_id=(options.get("device_id") or ""), days=int(options.get("days") or 365)
            )
        except ValueError as exc:
            raise CommandError(str(exc))

        self.stdout.write(self.style.SUCCESS(
            f"Minted edge credential for {school.slug} as {username} "
            f"(device={token.device.device_id}, expires {token.expires_at.isoformat()})."
        ))
        self.stdout.write("")
        self.stdout.write("Bearer token (shown ONCE — store as RMC_EDGE_CREDENTIAL on the box):")
        self.stdout.write(raw_token)
