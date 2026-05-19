"""
Backfill precomputed search_index columns (Google pillar hygiene).

Run after deploy or restore:
  python manage.py backfill_search_indexes
  python manage.py backfill_search_indexes --only students

With django-tenants (Render), student/document tables live in tenant schemas —
this command fans out across active tenants automatically.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection, transaction


def _table_has_column(table_name: str, column_name: str) -> bool:
    with connection.cursor() as cursor:
        columns = connection.introspection.get_table_description(cursor, table_name)
    return any(col.name == column_name for col in columns)


def _current_schema_name() -> str:
    return str(getattr(connection, "schema_name", "public") or "public")


class Command(BaseCommand):
    help = "Backfill StudentProfile.search_index and PortalFeatureItem.search_index rows."

    def add_arguments(self, parser):
        parser.add_argument(
            "--only",
            choices=("all", "students", "documents"),
            default="all",
            help="Limit backfill scope.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Bulk update batch size.",
        )

    def handle(self, *args, **options):
        only = options["only"]
        batch_size = max(50, int(options["batch_size"] or 500))
        use_tenants = bool(getattr(settings, "USE_DJANGO_TENANTS", False))

        if use_tenants and connection.vendor == "postgresql":
            self._backfill_all_tenant_schemas(only, batch_size)
        else:
            self._backfill_schema(only, batch_size, schema_label=_current_schema_name())

        self.stdout.write(self.style.SUCCESS("backfill_search_indexes: complete"))

    def _backfill_all_tenant_schemas(self, only: str, batch_size: int) -> None:
        from django_tenants.utils import get_tenant_model, tenant_context

        Tenant = get_tenant_model()
        clients = list(
            Tenant.objects.exclude(schema_name="public")
            .filter(schema_name__isnull=False)
            .order_by("schema_name")
        )
        if not clients:
            self.stdout.write(
                "  (no tenant schemas; skipping student/document search_index backfill)"
            )
            return

        for client in clients:
            schema = getattr(client, "schema_name", "") or ""
            with tenant_context(client):
                self._backfill_schema(
                    only,
                    batch_size,
                    schema_label=schema,
                )

    def _backfill_schema(self, only: str, batch_size: int, *, schema_label: str) -> None:
        if only in ("all", "students"):
            if not _table_has_column("people_studentprofile", "search_index"):
                self.stdout.write(
                    f"  {schema_label}: students skipped "
                    "(people_studentprofile.search_index missing — apply people.0051)"
                )
            else:
                count = self._backfill_students(batch_size)
                self.stdout.write(
                    f"  {schema_label}: students {count} search_index rows refreshed"
                )
        if only in ("all", "documents"):
            if not _table_has_column("portal_portalfeatureitem", "search_index"):
                self.stdout.write(
                    f"  {schema_label}: documents skipped "
                    "(portal_portalfeatureitem.search_index missing — apply portal migrations)"
                )
            else:
                count = self._backfill_documents(batch_size)
                self.stdout.write(
                    f"  {schema_label}: documents {count} search_index rows refreshed"
                )

    def _backfill_students(self, batch_size: int) -> int:
        from apps.people.models import StudentProfile
        from apps.people.student_search_index import build_student_search_index

        updated = 0
        batch: list[StudentProfile] = []
        for row in StudentProfile.objects.iterator(chunk_size=batch_size):
            row.search_index = build_student_search_index(row)
            batch.append(row)
            if len(batch) >= batch_size:
                with transaction.atomic():
                    StudentProfile.objects.bulk_update(batch, ["search_index"])
                updated += len(batch)
                batch = []
        if batch:
            with transaction.atomic():
                StudentProfile.objects.bulk_update(batch, ["search_index"])
            updated += len(batch)
        return updated

    def _backfill_documents(self, batch_size: int) -> int:
        from apps.portal.document_lifecycle import build_document_search_index
        from apps.portal.models import PortalFeatureItem

        updated = 0
        batch: list[PortalFeatureItem] = []
        for row in PortalFeatureItem.objects.iterator(chunk_size=batch_size):
            row.search_index = build_document_search_index(row)
            batch.append(row)
            if len(batch) >= batch_size:
                with transaction.atomic():
                    PortalFeatureItem.objects.bulk_update(batch, ["search_index"])
                updated += len(batch)
                batch = []
        if batch:
            with transaction.atomic():
                PortalFeatureItem.objects.bulk_update(batch, ["search_index"])
            updated += len(batch)
        return updated
