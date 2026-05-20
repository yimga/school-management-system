from django.test import SimpleTestCase

from apps.metadata.ddl_safety import (
    MetadataDdlForbiddenError,
    assert_no_ddl_in_sql,
    contains_forbidden_ddl,
    preview_governed_metadata_change,
)


class MetadataNoDdlSafetyTests(SimpleTestCase):
    def test_detects_alter_table(self):
        self.assertTrue(contains_forbidden_ddl("ALTER TABLE foo ADD COLUMN bar int"))

    def test_allows_select(self):
        self.assertFalse(contains_forbidden_ddl("SELECT id FROM metadata_entity"))

    def test_assert_raises_on_ddl(self):
        with self.assertRaises(MetadataDdlForbiddenError):
            assert_no_ddl_in_sql("DROP TABLE dynamic_field_value", context="test")

    def test_governed_preview_is_non_mutating(self):
        payload = preview_governed_metadata_change(
            [
                {
                    "entity": "Student",
                    "field": "nickname",
                    "owner": "metadata",
                    "action": "update",
                }
            ],
            scope="tenant",
            tenant_id="school-1",
        )
        self.assertTrue(payload["non_mutating"])
        self.assertTrue(payload["preview"]["non_mutating"])
        self.assertIn("rollback_posture", payload)
