"""Give every guardian-linked parent a SchoolMembership (offline-recovery backfill).

A parent who onboarded via a guardian invite (``claim_invite`` →
``link_guardian_via_invite``) or the admission-number wizard historically received
a login-capable ``User`` but NO ``SchoolMembership`` — only a ``StudentGuardian``
link. Such a parent is invisible to the tenant identity roster and, because
``can_reset_target`` requires a membership, cannot have their password reset by a
tenant admin from the UI — the exact offline-recovery hole this backfill closes for
accounts that predate the runtime fix in ``ensure_school_membership``.

Idempotent and safe to re-run. Dry-run by default; pass ``--apply`` to write.

    python manage.py backfill_guardian_memberships              # report only
    python manage.py backfill_guardian_memberships --apply       # write
    python manage.py backfill_guardian_memberships --schema gilead --apply

``StudentGuardian`` is a TENANT model (per-schema) while ``SchoolMembership`` is
SHARED (public schema), so on django-tenants this walks each tenant schema in
``tenant_context``. Under ``USE_DJANGO_TENANTS=0`` (RLS / SQLite) there is one
schema and it runs directly.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Backfill SchoolMembership for guardian-linked parents that lack one."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write memberships. Without this flag the command only reports.",
        )
        parser.add_argument(
            "--schema",
            default="",
            help="Limit to a single tenant schema name (django-tenants only).",
        )

    def handle(self, *args, **options):
        apply = bool(options.get("apply"))
        only_schema = (options.get("schema") or "").strip()

        clients = self._tenant_clients(only_schema)
        if clients is None:
            # Not running django-tenants — one schema, process directly.
            created, scanned = self._backfill_current_schema(apply)
            self._report(None, created, scanned)
            self._summary(apply, created)
            return

        total_created = 0
        for client in clients:
            from django_tenants.utils import tenant_context

            schema_name = (getattr(client, "schema_name", None) or "").strip()
            if not schema_name:
                continue
            with tenant_context(client):
                created, scanned = self._backfill_current_schema(apply)
            total_created += created
            self._report(schema_name, created, scanned)
        self._summary(apply, total_created)

    # ----------------------------------------------------------------- helpers
    def _tenant_clients(self, only_schema):
        """Return the tenant Client rows to walk, or ``None`` under RLS / single-schema mode.

        Gates on ``USE_DJANGO_TENANTS`` (the tenancy-mode SOT), NOT on import
        availability: under ``USE_DJANGO_TENANTS=0`` (RLS / SQLite) the ``Client``
        model imports fine but all rows live in one schema, so schema iteration
        would silently skip everything.
        """
        from django.conf import settings

        if not getattr(settings, "USE_DJANGO_TENANTS", False):
            return None
        try:
            from django_tenants.utils import tenant_context  # noqa: F401

            from apps.customers.models import Client
        except ImportError:
            return None
        qs = (
            Client.objects.exclude(schema_name="public")
            .filter(schema_name__isnull=False)
            .order_by("id")
        )
        if only_schema:
            qs = qs.filter(schema_name=only_schema)
        return list(qs)

    def _backfill_current_schema(self, apply):
        """Within the active schema, ensure a membership for each guardian. Returns (created, scanned)."""
        from apps.accounts.tenant_identity import ensure_school_membership
        from apps.people.models import StudentGuardian

        seen_pairs: set[tuple[int, int]] = set()
        created = 0
        scanned = 0
        links = (
            StudentGuardian.objects.filter(  # tenant-isolation-allow: per-schema guardian walk in tenant_context
                guardian_user__isnull=False
            )
            .select_related("guardian_user", "student", "student__school")
        )
        for link in links.iterator():
            guardian = link.guardian_user
            student = link.student
            school = getattr(student, "school", None)
            if guardian is None or school is None:
                continue
            pair = (guardian.pk, school.pk)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            scanned += 1
            if not apply:
                from apps.schools.models import SchoolMembership

                if not SchoolMembership.objects.filter(
                    user_id=guardian.pk, school_id=school.pk
                ).exists():
                    created += 1
                continue
            _membership, was_created = ensure_school_membership(
                guardian, school, role=guardian.role
            )
            if was_created:
                created += 1
        return created, scanned

    def _report(self, schema_name, created, scanned):
        label = f"[{schema_name}] " if schema_name else ""
        self.stdout.write(
            f"{label}scanned {scanned} guardian/school pair(s); "
            f"{created} membership(s) missing"
        )

    def _summary(self, apply, total_created):
        if apply:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Backfill complete — {total_created} membership(s) created."
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run — {total_created} membership(s) WOULD be created. "
                    "Re-run with --apply to write."
                )
            )
