"""Import a .rmcstaff bundle onto this deployment (pk-preserving, fail-closed).

Run this on the BOX. It is the explicit operator act that
``docs/EDGE_SYNC_IDENTITY_HOLD.md`` says provisioning staff requires -- "a feature, not a
sync-policy change, and it must never be implicit in a bundle apply". Nothing on the sync
rail can reach this code.

    python manage.py import_tenant_staff --in gilead.rmcstaff --expect-school-id <uuid>
    python manage.py import_tenant_staff --in gilead.rmcstaff --dry-run
    python manage.py import_tenant_staff --in gilead.rmcstaff --reset-passwords

pks are preserved, which is the point: once the rows exist with the same pks on both
sides, ordinary delta sync converges by UPDATE-by-pk (which the identity hold permits) and
the per-cycle "NOT applied" count for teachers falls to zero.
"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Import a .rmcstaff bundle (pk-preserving, signature-verified, transactional)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--in", dest="in_path", required=True, help="Source .rmcstaff path."
        )
        parser.add_argument(
            "--expect-school-id",
            dest="expect_school_id",
            default="",
            help="Refuse the import unless the bundle is for this school UUID.",
        )
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help=(
                "Land the accounts with an unusable password + must-change instead of "
                "carrying the hashes. Safer, but each teacher must set a password before "
                "they can sign in — which needs a reachable reset path on the box."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Verify the bundle and report what WOULD land. Writes nothing.",
        )

    def handle(self, *args, **options):
        from apps.lifecycle.staff_portability import (
            import_staff_bundle,
            inspect_staff_bundle,
        )

        path = Path(options["in_path"])
        if not path.exists():
            raise CommandError(f"Bundle not found: {path}")
        expect = (options.get("expect_school_id") or "").strip() or None
        data = path.read_bytes()

        if options.get("dry_run"):
            try:
                report = inspect_staff_bundle(data, expected_school_id=expect)
            except ValueError as exc:
                raise CommandError(f"Import would be refused: {exc}")
            collisions = report["collisions"]
            self.stdout.write(
                f"Would import {report['users']} login(s) and "
                f"{report['teachers']} teacher profile(s) for "
                f"{report['tenant_slug'] or report['school_id']}."
            )
            if collisions:
                self.stdout.write(
                    self.style.ERROR(
                        "  REFUSED: these pks belong to different accounts here — "
                        + "; ".join(collisions)
                    )
                )
            else:
                self.stdout.write(self.style.SUCCESS("  No pk collisions. Safe to run."))
            return

        try:
            result = import_staff_bundle(
                data,
                expected_school_id=expect,
                reset_passwords=bool(options.get("reset_passwords")),
            )
        except ValueError as exc:
            raise CommandError(f"Import refused: {exc}")

        self.stdout.write(
            self.style.SUCCESS(
                "Imported %d login(s) and %d teacher profile(s) for %s (passwords %s)."
                % (
                    result["users"],
                    result["teachers"],
                    result["tenant_slug"] or result["school_id"],
                    result["passwords"],
                )
            )
        )
        for field, count in sorted((result.get("dropped_references") or {}).items()):
            # Said out loud rather than left in the data: the sync rail will not supply
            # these later either, so an operator who is not told will never find out.
            self.stdout.write(
                self.style.WARNING(
                    f"  {count} teacher(s) lost their {field}: the target row does not "
                    "exist on this deployment and does not ride the sync rail."
                )
            )
        if result["passwords"] == "reset":
            self.stdout.write(
                "  Accounts landed with unusable passwords. Each teacher must set one "
                "before they can sign in."
            )
