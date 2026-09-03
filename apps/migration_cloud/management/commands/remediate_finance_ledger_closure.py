"""Backfill finance import→ledger closure for one tenant.

Issues DRAFT invoices with totals, syncs InvoiceLine rows, and posts ledger
entries for schools that imported fees before batch 1821 landed.

Usage::

    manage.py remediate_finance_ledger_closure --school gilead-tech --dry-run
    manage.py remediate_finance_ledger_closure --school gilead-tech --apply
"""

from __future__ import annotations

from contextlib import contextmanager

from django.core.management.base import BaseCommand, CommandError

from apps.schools.models import School


@contextmanager
def _tenant_schema(school):
    from apps.migration_cloud.schema_binding import resolve_school_schema_name

    schema_name = (resolve_school_schema_name(school) or "").strip()
    if not schema_name:
        raise CommandError(
            f"No tenant schema bound to school {getattr(school, 'subdomain', school)!r}."
        )
    try:
        from django_tenants.utils import schema_context
    except ImportError:
        schema_context = None
    if schema_context is None:
        yield schema_name
        return
    from django.db import connection

    if not hasattr(connection, "set_schema"):
        yield schema_name
        return
    with schema_context(schema_name):
        yield schema_name


class Command(BaseCommand):
    help = "Issue imported invoices and post ledger entries for one school."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            required=True,
            help="School id, subdomain, or slug.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report planned closure without writing.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Execute closure inside the tenant schema.",
        )

    def handle(self, *args, **options):
        if not options["dry_run"] and not options["apply"]:
            raise CommandError("Pass --dry-run or --apply.")

        school = self._resolve_school(options["school"])
        dry_run = bool(options["dry_run"])

        with _tenant_schema(school):
            from apps.migration_cloud.finance_ledger import (
                assess_finance_ledger_readiness,
                ensure_finance_ledger_closure,
            )

            before = assess_finance_ledger_readiness(school)
            self.stdout.write(f"Before: {before}")

            outcome = ensure_finance_ledger_closure(school, dry_run=dry_run)
            self.stdout.write(f"Closure: {outcome}")

            if not dry_run:
                after = assess_finance_ledger_readiness(school)
                self.stdout.write(f"After: {after}")

    def _resolve_school(self, token: str) -> School:
        token = str(token or "").strip()
        if not token:
            raise CommandError("--school is required.")
        for lookup in (
            {"pk": token} if token.isdigit() else None,
            {"subdomain": token},
            {"slug": token},
        ):
            if lookup is None:
                continue
            school = School.objects.filter(**lookup).first()
            if school is not None:
                return school
        raise CommandError(f"School not found: {token!r}")
