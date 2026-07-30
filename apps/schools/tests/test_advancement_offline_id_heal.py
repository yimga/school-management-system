from django.db import connection
from django.test import TestCase

from apps.schools.schema_repair import ensure_advancement_offline_id_columns


class AdvancementOfflineIdHealTests(TestCase):
    def test_ensure_columns_idempotent(self):
        # Tables created at HEAD already have client_offline_id → repair no-ops.
        self.assertFalse(ensure_advancement_offline_id_columns())
        self.assertFalse(ensure_advancement_offline_id_columns())

    def test_client_offline_id_present_after_migrate(self):
        for table in ("schools_advancementgift", "schools_inkinddonation"):
            with connection.cursor() as cursor:
                columns = {
                    col.name
                    for col in connection.introspection.get_table_description(
                        cursor, table
                    )
                }
            self.assertIn("client_offline_id", columns, msg=f"missing on {table}")

    def test_partial_unique_indexes_present_after_migrate(self):
        expected = {
            "schools_advancementgift": "uniq_advancementgift_donor_client_offline_id",
            "schools_inkinddonation": "uniq_inkinddonation_school_client_offline_id",
        }
        for table, index_name in expected.items():
            with connection.cursor() as cursor:
                constraints = connection.introspection.get_constraints(cursor, table)
            self.assertIn(index_name, constraints, msg=f"missing on {table}")
