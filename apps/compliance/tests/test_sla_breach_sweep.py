"""Pass 9.D smoke test: `compliance.mark_sla_breaches` Celery task.

Verifies the hourly sweep:
  - stamps `sla_breach_at` on overdue PENDING/RUNNING rows
  - does NOT stamp terminal-status rows (completed/failed/rejected)
  - is idempotent — re-running doesn't re-stamp already-stamped rows
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.compliance.models import EraseRequest, ExportJob
from apps.compliance.tasks import mark_sla_breaches
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class MarkSlaBreachesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.region, _ = RegionConfig.objects.get_or_create(
            code="TSL",
            defaults={
                "name": "SLA Test Region",
                "default_language": "en",
                "timezone": "UTC",
                "date_format": "DD/MM/YYYY",
            },
        )
        cls.school = School.objects.create(
            name="SLA Test School",
            slug="sla-test-school",
            subdomain="sla-test",
            is_active=True,
            default_region=cls.region,
        )
        cls.subject_user = User.objects.create_user(
            username="sla_subject",
            email="sla.subject@example.com",
            password="x",
            role=User.Role.STUDENT,
        )

    def _make_export(self, *, due_offset_days: int, status: str = "pending"):
        now = timezone.now()
        return ExportJob.objects.create(
            school=self.school,
            scope="user",
            status=status,
            due_at=now + timedelta(days=due_offset_days),
        )

    def _make_erase(self, *, due_offset_days: int, status: str = "pending"):
        now = timezone.now()
        return EraseRequest.objects.create(
            school=self.school,
            subject_user=self.subject_user,
            status=status,
            due_at=now + timedelta(days=due_offset_days),
        )

    def test_overdue_pending_export_gets_stamped(self):
        ej = self._make_export(due_offset_days=-1)
        stamped = mark_sla_breaches()
        self.assertEqual(stamped["exports"], 1)
        ej.refresh_from_db()
        self.assertIsNotNone(ej.sla_breach_at)

    def test_overdue_terminal_export_is_skipped(self):
        ej = self._make_export(due_offset_days=-1, status="completed")
        stamped = mark_sla_breaches()
        self.assertEqual(stamped["exports"], 0)
        ej.refresh_from_db()
        self.assertIsNone(ej.sla_breach_at)

    def test_future_due_export_is_not_stamped(self):
        ej = self._make_export(due_offset_days=+5)
        stamped = mark_sla_breaches()
        self.assertEqual(stamped["exports"], 0)
        ej.refresh_from_db()
        self.assertIsNone(ej.sla_breach_at)

    def test_overdue_pending_erase_gets_stamped(self):
        er = self._make_erase(due_offset_days=-2)
        stamped = mark_sla_breaches()
        self.assertEqual(stamped["erases"], 1)
        er.refresh_from_db()
        self.assertIsNotNone(er.sla_breach_at)

    def test_idempotent_second_run(self):
        ej = self._make_export(due_offset_days=-3)
        first = mark_sla_breaches()
        self.assertEqual(first["exports"], 1)
        second = mark_sla_breaches()
        # Second run finds no further unstamped overdue rows.
        self.assertEqual(second["exports"], 0)
        ej.refresh_from_db()
        self.assertIsNotNone(ej.sla_breach_at)
