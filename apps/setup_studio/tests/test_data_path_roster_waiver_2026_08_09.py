"""Seal: a roster waiver clears the data_path go-live blocker (2026-08-09).

The data_path step is the load-bearing launch blocker (execute_launch refuses
while any blocker is unmet). A brand-new school with no legacy data and no
roster yet could not go live at all. A durable, auditable "launch with no
students yet" waiver now clears it — while a MIGRATION waiver deliberately does
NOT (a school lacking only legacy data still enters its current roster).

These tests FAIL before setup_studio.services honors the roster waiver.
"""
from __future__ import annotations

from django.test import TestCase

from apps.schools.models import School
from apps.schools import onboarding_waiver as ow
from apps.setup_studio.services import _step_state_for_school


class DataPathRosterWaiverTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Empty Roster School",
            slug="empty-roster",
            subdomain="empty-roster",
            is_active=True,
            country_code="CM",
        )

    def _state(self):
        return _step_state_for_school(School.objects.get(pk=self.school.pk))

    def test_data_path_blocks_without_students_or_waiver(self):
        state = self._state()
        self.assertFalse(state["data_path"]["done"])
        self.assertTrue(state["data_path"]["is_blocker"])

    def test_roster_waiver_clears_data_path_blocker(self):
        ow.waive(self.school, ow.WAIVER_ROSTER, reason=ow.REASON_NO_STUDENTS_YET)
        state = self._state()
        self.assertTrue(state["data_path"]["done"])
        # Evidence reflects the waiver rather than "not imported yet".
        self.assertIn("waived", state["data_path"]["evidence"].lower())

    def test_migration_waiver_does_not_clear_data_path(self):
        # "No legacy data to migrate" must NOT silently satisfy the roster gate.
        ow.waive(self.school, ow.WAIVER_MIGRATION, reason=ow.REASON_NO_LEGACY_DATA)
        state = self._state()
        self.assertFalse(state["data_path"]["done"])

    def test_unwaiving_roster_reinstates_the_blocker(self):
        ow.waive(self.school, ow.WAIVER_ROSTER, reason=ow.REASON_NO_STUDENTS_YET)
        self.assertTrue(self._state()["data_path"]["done"])
        ow.unwaive(School.objects.get(pk=self.school.pk), ow.WAIVER_ROSTER)
        self.assertFalse(self._state()["data_path"]["done"])
