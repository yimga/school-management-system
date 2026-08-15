"""import_tenant_identities - recreate a school's user identities (edge-box side).

Consumes an ``.rmcidentity`` bundle produced by ``export_tenant_identities`` on the
cloud and recreates, on THIS deployment: the Users (password HASH copied verbatim ->
they log in with existing credentials), their SchoolMembership (role / owner flag),
and their MFA devices (confirmed TOTP with its secret, static backup codes, passkeys
-> authenticator apps keep working). The School PARENT must already exist at the
bundle's UUID (run ``import_sovereign_tenant`` first).

Everything runs inside one ``rls_bypass() + transaction.atomic()`` unit: only
SchoolMembership is FORCE-RLS, but the whole op is wrapped so a failure rolls back
cleanly. Idempotent: users are matched by their unique ``username``.

    python manage.py import_tenant_identities \
        --in gilead.rmcidentity --slug gilead-tech --dry-run
    python manage.py import_tenant_identities --in gilead.rmcidentity --slug gilead-tech

Requires the SAME SECRET_KEY as the exporting cloud (bundle is encrypted+signed with
SECRET_KEY bound to the school id); a mismatch fails closed BEFORE any decrypt/write.
"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Recreate a school's users + memberships + MFA from a signed identity bundle (edge box)."

    def add_arguments(self, parser):
        parser.add_argument("--in", dest="in_path", required=True, help="Source .rmcidentity bundle.")
        parser.add_argument("--slug", default="gilead-tech", help="Expected School slug on this box (sanity check).")
        parser.add_argument(
            "--expect-school-id",
            dest="expect_school_id",
            default="",
            help="Optional guard: refuse unless the bundle is for this school UUID.",
        )
        parser.add_argument(
            "--owner-role",
            dest="owner_role",
            default="ADMIN",
            help="Tenant role forced on is_school_owner users (default ADMIN; SUPERADMIN is redirected off tenant hosts).",
        )
        parser.add_argument(
            "--skip-mfa",
            action="store_true",
            help="Recreate accounts + memberships but NOT MFA devices (owners re-enroll on the box).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Verify + decrypt and report who WOULD be imported, without writing.",
        )

    def handle(self, *args, **opts):
        from apps.lifecycle.tenant_identity_portability import (
            import_tenant_identities,
            read_identity_payload,
        )
        from apps.schools.models import School, SchoolMembership

        in_path = Path(opts["in_path"])
        if not in_path.exists():
            raise CommandError(f"Identity bundle not found: {in_path}")

        expect = (opts.get("expect_school_id") or "").strip() or None
        skip_mfa = bool(opts["skip_mfa"])
        owner_role = (opts.get("owner_role") or "ADMIN").strip().upper()
        dry_run = bool(opts["dry_run"])
        slug = (opts.get("slug") or "").strip().lower()

        container_bytes = in_path.read_bytes()

        try:
            payload = read_identity_payload(container_bytes, expected_school_id=expect)
        except ValueError as exc:
            raise CommandError(f"Identity bundle refused (fail-closed): {exc}")

        school_id = str(payload["school_id"])
        identities = payload.get("identities", []) or []

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "Identity import -> school %s (%d identities)" % (school_id, len(identities))
            )
        )

        # Sanity: the box's School parent must exist at this UUID (and match --slug).
        school = School.objects.filter(id=school_id).first()
        if school is None:
            raise CommandError(
                "No School on this box with id=%s. Run import_sovereign_tenant first "
                "to create the parent, THEN import identities." % school_id
            )
        if slug and school.slug != slug:
            raise CommandError(
                "Bundle school id=%s resolves to slug %r on this box, not --slug %r."
                % (school_id, school.slug, slug)
            )

        for rec in identities:
            u = rec.get("user") or {}
            m = rec.get("membership") or {}
            flags = []
            if m.get("is_school_owner"):
                flags.append("owner")
            if u.get("is_superuser"):
                flags.append("superuser")
            if rec.get("totp"):
                flags.append("totp")
            if rec.get("static"):
                flags.append("backup-codes")
            if rec.get("passkeys"):
                flags.append("passkey")
            existing = "exists" if _user_exists(u.get("username")) else "new"
            self.stdout.write(
                "  - %s <%s> role=%s [%s] (%s)"
                % (
                    u.get("username", "?"),
                    u.get("email", ""),
                    u.get("role", ""),
                    ", ".join(flags) or "no-mfa",
                    existing,
                )
            )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "DRY RUN - would upsert %d users + memberships%s into school %s. Nothing written."
                    % (
                        len(identities),
                        "" if skip_mfa else " + MFA devices",
                        school.slug,
                    )
                )
            )
            return

        result = import_tenant_identities(
            container_bytes,
            expected_school_id=expect,
            owner_role=owner_role,
            skip_mfa=skip_mfa,
        )

        # Self-verify: the school must end up with at least one active owner.
        school.refresh_from_db()
        has_owner = SchoolMembership.has_active_owner(school)

        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(self.style.SUCCESS("  IDENTITIES IMPORTED"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(
            "  users: %d (new %d) | memberships: %d | active owners: %d"
            % (result["users"], result["created_users"], result["memberships"], result["owners"])
        )
        if not skip_mfa:
            self.stdout.write(
                "  MFA: totp=%d static=%d passkeys=%d"
                % (result["totp"], result["static"], result["passkeys"])
            )
        self.stdout.write("  accounts: %s" % ", ".join(result["usernames"]))
        if not has_owner:
            raise CommandError(
                "Import completed but the school has NO active owner - rolling nothing "
                "back is unsafe. Check the bundle's is_school_owner flags."
            )
        self.stdout.write(
            self.style.SUCCESS(
                "  VERIFIED: school has an active owner. Migrated users sign in with their "
                "existing passwords%s."
                % ("" if skip_mfa else " + authenticator codes")
            )
        )


def _user_exists(username) -> bool:
    if not username:
        return False
    from django.contrib.auth import get_user_model

    return get_user_model().objects.filter(username__iexact=username).exists()
