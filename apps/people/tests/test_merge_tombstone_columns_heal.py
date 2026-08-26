"""Merge tombstone column heal (migration 0064/0068 schema_repair family)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase

from apps.people.models import TeacherProfile
from apps.people.schema_repair import (
    ensure_people_merge_tombstone_columns,
    ensure_people_schema_current,
)

User = get_user_model()


class PeopleMergeTombstoneColumnsHealTests(TransactionTestCase):
    databases = {"default"}

    def test_ensure_merge_columns_idempotent(self):
        self.assertFalse(ensure_people_merge_tombstone_columns())
        self.assertFalse(ensure_people_merge_tombstone_columns())

    def test_ensure_people_schema_current_includes_merge_heal(self):
        self.assertFalse(ensure_people_schema_current())

    def test_merged_into_id_present_after_migrate(self):
        with connection.cursor() as cursor:
            columns = {
                col.name
                for col in connection.introspection.get_table_description(
                    cursor, "people_teacherprofile"
                )
            }
        self.assertIn("merged_into_id", columns)

    def test_schema_repair_heals_missing_merged_into_and_is_idempotent(self):
        table = TeacherProfile._meta.db_table
        with connection.cursor() as cursor:
            try:
                cursor.execute(
                    f"ALTER TABLE {connection.ops.quote_name(table)} "
                    f"DROP COLUMN {connection.ops.quote_name('merged_into_id')};"
                )
            except Exception:
                self.skipTest("SQLite build cannot DROP COLUMN — heal path not simulable")

        with connection.cursor() as cursor:
            existing = {
                col.name
                for col in connection.introspection.get_table_description(cursor, table)
            }
        self.assertNotIn("merged_into_id", existing)

        self.assertTrue(ensure_people_merge_tombstone_columns())

        with connection.cursor() as cursor:
            existing_after = {
                col.name
                for col in connection.introspection.get_table_description(cursor, table)
            }
        self.assertIn("merged_into_id", existing_after)

        self.assertFalse(ensure_people_merge_tombstone_columns())

    def test_teacher_profile_query_after_heal(self):
        user = User.objects.create_user(
            username="merge_heal_teacher",
            password="pw",
            role=getattr(User.Role, "TEACHER", "TEACHER"),
        )
        profile = TeacherProfile.objects.create(user=user, staff_id="MERGE-HEAL-1")
        self.assertIsNone(profile.merged_into_id)
