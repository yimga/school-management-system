"""Schema repair for academics 0028 school_id drift."""

from django.test import TestCase


class AcademicsSchemaRepairTests(TestCase):
    def test_ensure_academics_school_id_columns_idempotent(self):
        from apps.academics.schema_repair import ensure_academics_school_id_columns

        first = ensure_academics_school_id_columns()
        second = ensure_academics_school_id_columns()
        self.assertIsInstance(first, bool)
        self.assertFalse(second)
