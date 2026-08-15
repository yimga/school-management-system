"""export_tenant_identities - export a school's user identities (cloud side).

Produces a signed+encrypted ``.rmcidentity`` bundle of every User scoped to the
school (via SchoolMembership), their membership (role / owner / primary), and their
MFA devices (confirmed TOTP + secret key, static backup codes, passkeys). Import it
on the edge box with ``import_tenant_identities`` so the cloud's real admins/staff
sign in with their EXISTING credentials and authenticator apps.

Identities live in the shared/public schema, so this needs NO django-tenants
schema_context - it reads correctly from the default connection.

    python manage.py export_tenant_identities --slug gilead-tech --out gilead.rmcidentity

The bundle is encrypted+HMAC-signed with SECRET_KEY bound to the school id, so the
importing box MUST share the same SECRET_KEY (fail-closed on mismatch).
"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Export a school's user identities + memberships + MFA to a signed bundle (cloud side)."

    def add_arguments(self, parser):
        parser.add_argument("--slug", default="", help="School slug to export (or use --school-id).")
        parser.add_argument("--school-id", dest="school_id", default="", help="School UUID (overrides --slug).")
        parser.add_argument("--out", required=True, help="Output path for the .rmcidentity bundle.")

    def handle(self, *args, **opts):
        from apps.lifecycle.tenant_identity_portability import (
            export_tenant_identities,
            read_identity_payload,
        )
        from apps.schools.models import School

        slug = (opts.get("slug") or "").strip().lower()
        school_id = (opts.get("school_id") or "").strip()
        if not slug and not school_id:
            raise CommandError("Provide --slug or --school-id.")

        if school_id:
            school = School.objects.filter(id=school_id).first()
        else:
            school = School.objects.filter(slug=slug).first()
        if school is None:
            raise CommandError(f"School not found (slug={slug!r} school_id={school_id!r}).")

        self.stdout.write(
            "Exporting identities for school %s (slug=%s, id=%s)..."
            % (school.name, school.slug, school.id)
        )

        blob = export_tenant_identities(school)

        out_path = Path(opts["out"])
        out_path.write_bytes(blob)

        # Summarize exactly what the bundle carries (decrypt-in-process; same secret).
        payload = read_identity_payload(blob, expected_school_id=str(school.id))
        identities = payload.get("identities", []) or []
        self.stdout.write(self.style.SUCCESS(f"Wrote {len(blob)} bytes -> {out_path}"))
        self.stdout.write(f"  identities: {len(identities)}")
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
            self.stdout.write(
                "    - %s <%s> role=%s [%s]"
                % (
                    u.get("username", "?"),
                    u.get("email", ""),
                    u.get("role", ""),
                    ", ".join(flags) or "no-mfa",
                )
            )
        self.stdout.write(
            "Transfer this file to the box and run: import_tenant_identities --in <file> --slug %s"
            % school.slug
        )
