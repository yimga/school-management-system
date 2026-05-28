"""Bulk school operator action service tests."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from django.test import TestCase

from apps.schools.bulk_operator_actions import (
    DESTRUCTIVE_CONFIRM_PHRASE,
    bulk_apply_school_actions,
)
from apps.schools.models import School


class BulkOperatorActionsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Bulk Test School",
            slug="bulk-test-school",
            subdomain="bulktest",
            is_active=True,
            is_approved=True,
        )

    def test_freeze_requires_no_confirm_phrase(self):
        outcome = bulk_apply_school_actions(
            school_ids=[self.school.pk],
            action="freeze",
            reason="STORAGE",
            actor=None,
        )
        self.assertTrue(outcome["ok"])
        self.assertEqual(outcome["succeeded"], 1)
        self.school.refresh_from_db()
        self.assertTrue(self.school.is_frozen)

    def test_begin_offboarding_requires_confirm_phrase(self):
        with self.assertRaises(ValueError):
            bulk_apply_school_actions(
                school_ids=[self.school.pk],
                action="begin_offboarding",
                actor=None,
                confirm_phrase="wrong",
            )

    @patch("apps.schools.bulk_operator_actions.run_wind_down_deactivate")
    @patch("apps.schools.bulk_operator_actions.operator_schedule_purge")
    @patch("apps.schools.bulk_operator_actions.provisioning_in_flight", return_value=False)
    @patch("apps.schools.bulk_operator_actions.legal_hold_active", return_value=(False, None))
    def test_begin_offboarding_with_phrase(
        self, _hold, _prov, schedule_purge, wind_down
    ):
        wind_down.return_value = {"message": "Deactivated."}
        schedule_purge.return_value = {"scheduled_purge_at": "2099-01-01"}
        outcome = bulk_apply_school_actions(
            school_ids=[self.school.pk],
            action="begin_offboarding",
            actor=None,
            confirm_phrase=DESTRUCTIVE_CONFIRM_PHRASE,
        )
        self.assertTrue(outcome["ok"])
        wind_down.assert_called_once()
        schedule_purge.assert_called_once()

    @patch("apps.schools.bulk_operator_actions.dry_run_purge")
    def test_purge_dry_run(self, dry_run_purge):
        from apps.schools.tenant_offboarding import PurgePreview

        dry_run_purge.return_value = PurgePreview(
            school_slug=self.school.slug,
            school_id=str(self.school.id),
            inventory={"students": 1},
            row_total=1,
            manifest_path="/tmp/manifest.json",
            schema_name=None,
            provisioning_in_flight=False,
            legal_hold_active=False,
            legal_hold_until=None,
            purge_blocked_reasons=[],
        )
        outcome = bulk_apply_school_actions(
            school_ids=[self.school.pk],
            action="purge_dry_run",
            actor=None,
            confirm_phrase="DRY RUN PURGE",
        )
        self.assertTrue(outcome["ok"])
        dry_run_purge.assert_called_once()

    def test_apply_purge_not_allowed_on_bulk_list(self):
        with self.assertRaisesMessage(ValueError, "Unsupported bulk action: apply_purge"):
            bulk_apply_school_actions(
                school_ids=[self.school.pk],
                action="apply_purge",
                actor=None,
                confirm_phrase="DELETE",
            )

    def test_missing_school_reported(self):
        missing_id = uuid.uuid4()
        outcome = bulk_apply_school_actions(
            school_ids=[missing_id],
            action="activate",
            actor=None,
        )
        self.assertEqual(outcome["succeeded"], 0)
        self.assertEqual(outcome["failed"], 1)
        self.assertFalse(outcome["results"][0]["ok"])
