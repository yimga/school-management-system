"""Verify the tenant-aware terminology cascade is wired end-to-end.

Proof command for the `vocabulary-injector` lifecycle capability
(docs/GLOCAL_SOVEREIGNTY_PLAN.md, Wave A). Asserts the public surface of
`apps.siteconfig.terminology_service` is intact and the registry resolves a
default term without a tenant, then — if `--school <id>` is given — prints the
full cascade resolution for that school.

Read-only. No DB writes. Emits no PII (only term labels + school id).

    python manage.py verify_terminology_cascade
    python manage.py verify_terminology_cascade --school <uuid> --strict
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.siteconfig import terminology_service as ts
from apps.siteconfig.lexicon_catalog import LEXICON_REGISTRY


class Command(BaseCommand):
    help = "Verify the terminology (vocabulary-injector) cascade is wired."

    def add_arguments(self, parser):
        parser.add_argument(
            "--school",
            default=None,
            help="Optional School id/slug to describe full cascade resolution for.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Exit non-zero if any default key fails to resolve.",
        )

    def handle(self, *args, **options):
        failures: list[str] = []

        # 1. Public surface intact.
        for name in (
            "resolve_term",
            "resolve_all_terms",
            "get_effective_terminology_for_school",
            "describe_terminology_resolution",
            "TERMINOLOGY_KEYS",
            "DEFAULT_TERMINOLOGY",
        ):
            if not hasattr(ts, name):
                failures.append(f"terminology_service missing public name: {name}")

        # 2. Registry populated + default keys present.
        if not LEXICON_REGISTRY:
            failures.append("LEXICON_REGISTRY is empty (no default vocabulary).")
        missing_defaults = sorted(ts.TERMINOLOGY_KEYS - set(ts.DEFAULT_TERMINOLOGY))
        if missing_defaults:
            failures.append(f"DEFAULT_TERMINOLOGY missing keys: {missing_defaults}")

        # 3. Registry-default resolution works without a tenant.
        for key in sorted(ts.TERMINOLOGY_KEYS):
            try:
                label = ts.resolve_term(None, key)
            except Exception as exc:  # noqa: BLE001 - surfaced as a failure line, not swallowed
                failures.append(f"resolve_term(None, {key!r}) raised {exc!r}")
                continue
            if not label:
                failures.append(f"resolve_term(None, {key!r}) returned empty.")
            else:
                self.stdout.write(f"  default  {key:<12} -> {label}")

        # 4. Optional per-school cascade description.
        school_ref = options.get("school")
        if school_ref:
            from apps.schools.models import School

            school = (
                School.objects.filter(pk=school_ref).first()
                or School.objects.filter(slug=school_ref).first()
            )
            if school is None:
                raise CommandError(f"No School matches {school_ref!r}.")
            self.stdout.write("")
            self.stdout.write(ts.describe_terminology_resolution(school))

        if failures:
            for line in failures:
                self.stderr.write(self.style.ERROR(line))
            if options.get("strict"):
                raise CommandError(f"terminology cascade verification failed ({len(failures)}).")
            self.stdout.write(self.style.WARNING(f"{len(failures)} issue(s) found (non-strict)."))
            return

        self.stdout.write(self.style.SUCCESS("terminology cascade OK"))
