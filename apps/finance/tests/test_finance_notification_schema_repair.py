"""Finance notification column heal (migration 0071 + 0072 schema_repair family).

Covers the drift class where ``0071`` is recorded but ``dismissed_at`` /
``expires_at`` / ``school_id`` never physically landed — the notification bell
and unread-count API 500 until ``ensure_finance_notification_columns`` runs.
"""

from __future__ import annotations

from django.db import connection
from django.test import TransactionTestCase

from apps.accounts.models import User
from apps.finance.models import Notification
from apps.finance.schema_repair import ensure_finance_notification_columns
from apps.test_utils.seed_preserving import RestoresSeedCatalogMixin


class FinanceNotificationSchemaRepairTests(RestoresSeedCatalogMixin, TransactionTestCase):
    databases = {"default"}

    def setUp(self):
        self.user = User.objects.create_user(username="notif_schema", password="pw")
        Notification.objects.create(
            recipient=self.user,
            title="Probe",
            message="schema repair contract",
        )

    def _drop_notification_drift_columns(self) -> None:
        table = Notification._meta.db_table
        with connection.cursor() as cursor:
            for col in ("dismissed_at", "expires_at", "school_id"):
                try:
                    cursor.execute(
                        f'ALTER TABLE {connection.ops.quote_name(table)} '
                        f"DROP COLUMN {connection.ops.quote_name(col)};"
                    )
                except Exception:
                    # SQLite < 3.35 or column already absent — skip that column.
                    pass

    def test_schema_repair_heals_missing_columns_and_is_idempotent(self):
        self._drop_notification_drift_columns()

        with connection.cursor() as cursor:
            existing = {
                col.name
                for col in connection.introspection.get_table_description(
                    cursor, Notification._meta.db_table
                )
            }
        missing_before = {
            c
            for c in ("dismissed_at", "expires_at", "school_id")
            if c not in existing
        }
        if not missing_before:
            self.skipTest("SQLite build cannot DROP COLUMN — heal path not simulable")

        self.assertTrue(ensure_finance_notification_columns())

        with connection.cursor() as cursor:
            existing_after = {
                col.name
                for col in connection.introspection.get_table_description(
                    cursor, Notification._meta.db_table
                )
            }
        for col in ("dismissed_at", "expires_at", "school_id"):
            self.assertIn(col, existing_after)

        self.assertFalse(ensure_finance_notification_columns())

    def test_healthy_schema_repair_is_noop(self):
        self.assertFalse(ensure_finance_notification_columns())
