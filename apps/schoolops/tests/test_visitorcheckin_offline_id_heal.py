from django.db import connection
from django.test import TestCase

from apps.schoolops.schema_repair import ensure_visitorcheckin_offline_id_column


class VisitorCheckInOfflineIdHealTests(TestCase):
    def test_ensure_column_idempotent(self):
        # Table created at HEAD already has client_offline_id → repair is a no-op.
        self.assertFalse(ensure_visitorcheckin_offline_id_column())
        self.assertFalse(ensure_visitorcheckin_offline_id_column())

    def test_client_offline_id_present_after_migrate(self):
        with connection.cursor() as cursor:
            columns = {
                col.name
                for col in connection.introspection.get_table_description(
                    cursor, "schools_visitorcheckin"
                )
            }
        self.assertIn("client_offline_id", columns)

    def test_partial_unique_index_present_after_migrate(self):
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(
                cursor, "schools_visitorcheckin"
            )
        self.assertIn("uniq_visitorcheckin_school_offline_id", constraints)
