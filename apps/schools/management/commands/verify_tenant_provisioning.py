"""Read-only sign-off that a PROVISIONED tenant school is fully correct.

This is the staging/Postgres complement to the local end-to-end test: after you
provision a test school the normal way (which, on Postgres, exercises the real
django-tenants schema build that the sqlite dev box can't), run this to get a
definitive PASS/FAIL on whether that tenant is actually complete.

It READS ONLY — it never creates, mutates, or drops anything, so it is safe to
run against staging or production. (The codebase intentionally never auto-drops
tenant schemas; this tool respects that.)

    manage.py verify_tenant_provisioning --slug <slug>
    manage.py verify_tenant_provisioning --school-id <id>

Checks: school active; (SCHEMA mode) tenant Client + Postgres schema exist;
academic year / terms / subjects / classrooms / department seeded; a COMPLETED
provisioning event with no FAILED event. Exits non-zero if any check fails so it
is usable from CI / deploy scripts.
"""

from __future__ import annotations

from contextlib import contextmanager

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


@contextmanager
def _seed_query_context(schema_mode, client):
    """In SCHEMA mode the seed rows live inside the tenant schema, so query them
    there; in shared-DB / RLS mode they are in the public schema (school FK)."""
    if schema_mode and client is not None:
        try:
            from django_tenants.utils import tenant_context

            with tenant_context(client):
                yield True
                return
        except Exception:  # noqa: BLE001 - fall back to current schema
            pass
    yield False


class Command(BaseCommand):
    help = "Read-only verification that a provisioned tenant school is complete."

    def add_arguments(self, parser):
        parser.add_argument("--slug", type=str, help="School slug to verify")
        parser.add_argument("--school-id", type=str, help="School id to verify")

    def handle(self, *args, **options):
        from apps.schools.models import School, SchoolProvisioningEvent

        slug = (options.get("slug") or "").strip()
        school_id = (options.get("school_id") or "").strip()
        if not slug and not school_id:
            raise CommandError("Provide --slug or --school-id")

        try:
            school = (
                School.objects.get(slug=slug)
                if slug
                else School.objects.get(pk=school_id)
            )
        except School.DoesNotExist as exc:
            raise CommandError(f"School not found: {exc}")

        results: list[tuple[bool, str, str]] = []

        def check(ok, label, detail=""):
            results.append((bool(ok), label, detail))

        # 1. Activated.
        check(getattr(school, "is_active", False), "school is active")

        # 2. Tenant schema actually built (SCHEMA mode / Postgres only).
        schema_mode = (
            bool(getattr(settings, "USE_DJANGO_TENANTS", False))
            and connection.vendor == "postgresql"
        )
        client = None
        if schema_mode:
            from apps.customers.models import Client
            from apps.customers.repositories.schema_provisioning_repository import (
                schema_exists,
            )

            client = Client.objects.filter(school=school).first()
            if client is None:
                check(False, "tenant Client row exists", "no customers.Client for school")
            else:
                check(
                    schema_exists(client.schema_name),
                    f"tenant Postgres schema exists ({client.schema_name})",
                )
        else:
            self.stdout.write(
                "  (shared-DB / non-Postgres mode — tenant schema build check is "
                "Postgres-only and is skipped here)"
            )

        # 3. Seed artifacts (queried in the right schema context).
        from apps.academics.models import (
            AcademicYear,
            Classroom,
            Department,
            Subject,
            Term,
        )

        with _seed_query_context(schema_mode, client) as in_tenant_schema:
            if schema_mode and in_tenant_schema:
                # Inside the tenant schema there is exactly one school's data.
                check(AcademicYear.objects.exists(), "academic year seeded")
                check(Term.objects.exists(), "terms seeded")
                check(Subject.objects.exists(), "subjects seeded")
                check(Classroom.objects.exists(), "classrooms seeded")
                check(Department.objects.exists(), "department seeded")
            else:
                check(AcademicYear.objects.filter(school=school).exists(), "academic year seeded")
                check(Term.objects.filter(school=school).exists(), "terms seeded")
                check(Subject.objects.filter(school=school).exists(), "subjects seeded")
                check(Classroom.objects.filter(school=school).exists(), "classrooms seeded")
                check(Department.objects.filter(school=school).exists(), "department seeded")

        # 4. Provisioning event log.
        check(
            SchoolProvisioningEvent.objects.filter(
                school=school, event_type="COMPLETED"
            ).exists(),
            "COMPLETED provisioning event recorded",
        )
        failed = SchoolProvisioningEvent.objects.filter(
            school=school, event_type="FAILED"
        ).order_by("-created_at")
        first_failed = failed.first()
        check(
            not failed.exists(),
            "no FAILED provisioning event",
            (getattr(first_failed, "message", "") or "") if first_failed else "",
        )

        # Report.
        self.stdout.write("")
        all_ok = True
        for ok, label, detail in results:
            mark = self.style.SUCCESS("PASS") if ok else self.style.ERROR("FAIL")
            line = f"  {mark}  {label}"
            if detail and not ok:
                line += f"  — {detail}"
            self.stdout.write(line)
            all_ok = all_ok and ok

        self.stdout.write("")
        if all_ok:
            self.stdout.write(
                self.style.SUCCESS(
                    f"OK: tenant '{school.slug}' is fully provisioned"
                    + (" (incl. Postgres schema build)." if schema_mode else ".")
                )
            )
        else:
            raise CommandError(
                f"Tenant '{school.slug}' has provisioning gaps (see FAIL lines above)."
            )
