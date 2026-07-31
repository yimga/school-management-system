"""Import a tenant .rmcbundle into this deployment (pk-preserving, fail-closed).

Loads a full-fidelity tenant export produced by ``export_tenant_bundle`` — e.g.
onto a fresh on-prem edge box. The signature (and bound school id) is verified
before anything is decrypted or written; the load is transactional. See
docs/plans/TIER3_TENANT_PORTABILITY_AND_EDGE_SYNC.md.

    python manage.py import_tenant_bundle --in gilead.rmcbundle
"""
from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Import a tenant .rmcbundle (pk-preserving, signature-verified, transactional)."

    def add_arguments(self, parser):
        parser.add_argument("--in", dest="in_path", required=True, help="Source .rmcbundle path.")
        parser.add_argument(
            "--expect-school-id",
            dest="expect_school_id",
            default="",
            help="Optional: refuse the import unless the bundle is for this school UUID.",
        )

    def handle(self, *args, **options):
        from apps.lifecycle.tenant_portability import import_tenant_bundle

        path = Path(options["in_path"])
        if not path.exists():
            raise CommandError(f"Bundle not found: {path}")

        expect = (options.get("expect_school_id") or "").strip() or None
        try:
            result = import_tenant_bundle(path.read_bytes(), expected_school_id=expect)
        except ValueError as exc:
            raise CommandError(f"Import refused: {exc}")

        self.stdout.write(
            self.style.SUCCESS(
                "Imported %s (%s mode): %d rows across %d tables."
                % (result["tenant_slug"] or result["school_id"], result["mode"],
                   result["total"], len(result["imported"]))
            )
        )
        if result.get("skipped"):
            self.stdout.write(self.style.WARNING(f"  skipped (unscopable in RLS): {len(result['skipped'])} model(s)"))
        if result.get("errored"):
            self.stdout.write(self.style.ERROR(f"  errored on export: {len(result['errored'])} model(s) — {list(result['errored'])[:5]}"))
