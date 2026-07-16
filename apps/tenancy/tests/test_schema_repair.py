"""Tests for the generic tenant-app ``school`` FK column heal.

Covers the exact drift the academics ``AcademicYear.school_id`` 500 exposed:
a tenant schema missing a retrofit ``school`` FK column. The heal must re-add it,
be a no-op on a healthy schema, be idempotent, and only ever touch real
``school`` -> schools.School FK fields.
"""

from django.db import connection
from django.test import TransactionTestCase

from apps.tenancy.schema_repair import _is_school_fk, ensure_app_school_id_columns


def _columns(table: str) -> set[str]:
    with connection.cursor() as cursor:
        return {c.name for c in connection.introspection.get_table_description(cursor, table)}


class IsSchoolFkTests(TransactionTestCase):
    def test_detects_school_fk_and_rejects_others(self):
        from apps.academics.models import AcademicYear, Incident

        self.assertTrue(_is_school_fk(AcademicYear._meta.get_field("school")))
        self.assertTrue(_is_school_fk(Incident._meta.get_field("school")))
        self.assertFalse(_is_school_fk(AcademicYear._meta.get_field("id")))
        # a plain char/date field is never a school FK
        self.assertFalse(_is_school_fk(AcademicYear._meta.get_field("start_date")))


class EnsureAppSchoolIdColumnsTests(TransactionTestCase):
    def test_unknown_app_is_noop(self):
        self.assertEqual(ensure_app_school_id_columns("definitely_not_an_app"), [])

    def test_healthy_schema_is_noop(self):
        # academics tables already carry school_id after migrations → nothing healed
        self.assertEqual(ensure_app_school_id_columns("academics"), [])

    def test_heals_dropped_column_then_idempotent(self):
        from apps.academics.models import Incident

        field = Incident._meta.get_field("school")
        table = Incident._meta.db_table
        col = field.column

        # Simulate the drift: drop the retrofit school FK column.
        with connection.schema_editor() as editor:
            editor.remove_field(Incident, field)
        self.assertNotIn(col, _columns(table))

        healed = ensure_app_school_id_columns("academics")
        self.assertIn(f"{table}.{col}", healed)
        self.assertIn(col, _columns(table))

        # Second run is a no-op (idempotent).
        self.assertEqual(ensure_app_school_id_columns("academics"), [])
