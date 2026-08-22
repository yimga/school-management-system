"""Operator HTML quarantine retry semantics align with tenant + REST (OR gate)."""

from __future__ import annotations

import inspect

from django.test import SimpleTestCase


class OperatorRetrySemanticsTests(SimpleTestCase):
    def test_operator_per_row_retry_uses_or_not_and(self):
        from apps.migration_cloud import views

        src = inspect.getsource(views.MigrationCloudQuarantineResolveView.post)
        self.assertIn("payload.get(\"auto_retry\") or outcome.get(\"queue_reimport\")", src)
        self.assertNotIn(
            "outcome.get(\"queue_reimport\") and payload.get(\"auto_retry\")",
            src,
        )
