"""Tests for the hardening-wave additions: Celery task wrapper, cleanup
management command, AI plan endpoint (deterministic path), attach-source
view, bind-school view.

AI narrative is not exercised here — the test environment has the
gateway disabled, so `generate_migration_plan` returns the deterministic
summary with `ai_available=False`. The fact that the deterministic path
is ALWAYS useful is the contract being locked in.
"""

from __future__ import annotations

from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.migration_cloud.ai_bridge import generate_migration_plan
from apps.migration_cloud.celery_tasks import advance_bundle_task
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle


def _operator():
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username="ops-hard@example.com",
        defaults={"email": "ops-hard@example.com", "is_staff": True, "is_superuser": True},
    )
    user.set_password("x")
    user.save()
    return user


class CeleryTaskTests(TestCase):
    """In tests CELERY_TASK_ALWAYS_EAGER = True so `.delay()` runs inline."""

    def test_advance_task_handles_missing_bundle(self) -> None:
        result = advance_bundle_task.delay(999999, True).get(disable_sync_subtasks=False)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "bundle_not_found")


class AIPlanEndpointTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = _operator()
        self.client = Client()
        self.client.force_login(self.user)
        self.bundle = MigrationBundle.objects.create(
            label="plan test",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="plan-test",
            status=BundleStatus.MAPPED,
            discovery_summary={
                "source": {"chosen": "unknown_custom", "method": "fallback"},
                "per_artifact_domain": {
                    "students.csv": {"domain": "students"},
                    "grades.csv": {"domain": "grades"},
                },
            },
            mapping_summary={
                "per_artifact": {
                    "students.csv": [
                        {"source_column": "id", "canonical_field": "student.id", "confidence": 0.95},
                        {"source_column": "homeroom", "canonical_field": "custom_fields.homeroom", "confidence": 0.6},
                    ],
                },
            },
        )

    def test_ai_plan_returns_deterministic_summary_even_without_ai(self) -> None:
        url = reverse("migration_cloud_super:bundle_ai_plan", kwargs={"bundle_id": self.bundle.pk})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        plan = resp.json()["plan"]
        self.assertEqual(plan["source"], "unknown_custom")
        self.assertEqual(plan["mapping_stats"]["high_confidence"], 1)
        self.assertEqual(plan["mapping_stats"]["custom_fields"], 1)
        self.assertIn("students", plan["domain_breakdown"])
        # unknown_custom should produce a review-burden risk flag
        self.assertTrue(any("known vendor" in f for f in plan["risk_flags"]))
        # Stages list must reflect MAPPED status.
        statuses = {s["name"]: s["status"] for s in plan["stages"]}
        self.assertEqual(statuses["MAPPED"], "current")
        self.assertEqual(statuses["PENDING"], "done")

    def test_generate_migration_plan_unit(self) -> None:
        """Direct call (no HTTP) — locks the dict shape."""
        plan = generate_migration_plan(bundle=self.bundle)
        self.assertIn("source", plan)
        self.assertIn("stages", plan)
        self.assertIn("mapping_stats", plan)
        self.assertIn("risk_flags", plan)
        # AI not available in test env → narrative is None, flag is False.
        self.assertFalse(plan["ai_available"])
        self.assertIsNone(plan["narrative"])


class AttachSourceViewTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = _operator()
        self.client = Client()
        self.client.force_login(self.user)
        self.bundle = MigrationBundle.objects.create(
            label="attach test",
            intake_method=IntakeMethod.DATABASE,
            idempotency_key="attach-test",
            status=BundleStatus.PENDING,
        )
        self.url = reverse(
            "migration_cloud_super:bundle_attach_source", kwargs={"bundle_id": self.bundle.pk}
        )

    def test_get_renders_form(self) -> None:
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "intake_source_uri")

    def test_post_rejects_unknown_dsn_scheme(self) -> None:
        resp = self.client.post(self.url, data={"intake_source_uri": "ftp://example.com/db"})
        self.assertEqual(resp.status_code, 400)
        self.bundle.refresh_from_db()
        self.assertEqual(self.bundle.intake_source_uri, "")

    def test_post_writes_uri(self) -> None:
        resp = self.client.post(self.url, data={
            "intake_source_uri": "postgresql://u:p@host/db",
            "notes": "Read replica, staging only",
        })
        self.assertEqual(resp.status_code, 302)
        self.bundle.refresh_from_db()
        self.assertEqual(self.bundle.intake_source_uri, "postgresql://u:p@host/db")
        self.assertIn("attached_source_notes", self.bundle.size_summary)


class BindSchoolViewTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        self.user = _operator()
        self.client = Client()
        self.client.force_login(self.user)
        self.bundle = MigrationBundle.objects.create(
            label="bind test",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="bind-test",
            status=BundleStatus.PENDING,
            school=None,
        )

    def test_portal_shell_forbidden(self) -> None:
        url = reverse(
            "migration_cloud_portal:bundle_bind_school", kwargs={"bundle_id": self.bundle.pk}
        )
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)

    def test_invalid_school_id_returns_400(self) -> None:
        url = reverse(
            "migration_cloud_super:bundle_bind_school", kwargs={"bundle_id": self.bundle.pk}
        )
        resp = self.client.post(url, data={"school_id": "not-a-number"})
        self.assertEqual(resp.status_code, 400)


class CleanupCommandTests(TestCase):
    def test_dry_run_does_not_delete(self) -> None:
        with TemporaryDirectory() as media_root:
            old_day = (date.today() - timedelta(days=60)).isoformat()
            slot = Path(media_root) / "migration_cloud" / "intake" / old_day / "abcd1234"
            slot.mkdir(parents=True)
            (slot / "students.csv").write_bytes(b"id,name\n1,Ada\n")

            buf = StringIO()
            with override_settings(MEDIA_ROOT=media_root):
                call_command(
                    "cleanup_intake_uploads",
                    "--days", "30", "--dry-run",
                    stdout=buf,
                )
            out = buf.getvalue()
            self.assertIn("would remove", out)
            self.assertTrue(slot.exists(), "dry-run must not delete")

    def test_zero_days_refused(self) -> None:
        with TemporaryDirectory() as media_root:
            buf = StringIO()
            with override_settings(MEDIA_ROOT=media_root):
                call_command("cleanup_intake_uploads", "--days", "0", stdout=buf)
            self.assertIn("No-op", buf.getvalue())

    def test_real_delete_removes_old_slot(self) -> None:
        with TemporaryDirectory() as media_root:
            old_day = (date.today() - timedelta(days=45)).isoformat()
            slot = Path(media_root) / "migration_cloud" / "intake" / old_day / "feedfeed"
            slot.mkdir(parents=True)
            (slot / "old.csv").write_bytes(b"x\n1\n")

            recent_day = (date.today() - timedelta(days=2)).isoformat()
            recent_slot = Path(media_root) / "migration_cloud" / "intake" / recent_day / "newnew"
            recent_slot.mkdir(parents=True)
            (recent_slot / "fresh.csv").write_bytes(b"x\n2\n")

            buf = StringIO()
            with override_settings(MEDIA_ROOT=media_root):
                call_command("cleanup_intake_uploads", "--days", "30", stdout=buf)
            self.assertFalse(slot.exists(), "old slot should be removed")
            self.assertTrue(recent_slot.exists(), "recent slot must be preserved")
