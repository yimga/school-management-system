from django.db import connection
from django.test import TestCase

from apps.academics.schema_repair import ensure_academics_offline_sync_columns

_OFFLINE_TABLES = (
    "academics_classroom",
    "academics_attendance",
)


class AcademicsOfflineSyncColumnsHealTests(TestCase):
    def test_ensure_columns_idempotent(self):
        # Tables created at HEAD already have client_offline_id → repair is a no-op.
        self.assertFalse(ensure_academics_offline_sync_columns())
        self.assertFalse(ensure_academics_offline_sync_columns())

    def test_client_offline_id_present_after_migrate(self):
        for table in _OFFLINE_TABLES:
            with connection.cursor() as cursor:
                columns = {
                    col.name
                    for col in connection.introspection.get_table_description(
                        cursor, table
                    )
                }
            self.assertIn(
                "client_offline_id",
                columns,
                msg=f"{table} missing client_offline_id after migrate",
            )

    def test_partial_unique_index_present_after_migrate(self):
        expected = {
            "academics_classroom": "uniq_classroom_school_offline_id",
            "academics_attendance": "uniq_attendance_school_offline_id",
        }
        for table, index_name in expected.items():
            with connection.cursor() as cursor:
                constraints = connection.introspection.get_constraints(cursor, table)
            self.assertIn(
                index_name,
                constraints,
                msg=f"{table} missing {index_name} after migrate",
            )
