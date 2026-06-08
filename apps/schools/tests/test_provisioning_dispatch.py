from unittest.mock import patch

from django.test import TestCase

from apps.schools.models import School
from apps.schools.tasks import complete_provisioning_for_school, dispatch_provision_school


class ProvisioningDispatchTests(TestCase):
    def test_dispatch_falls_back_to_sync_when_queue_is_unavailable(self):
        school = School.objects.create(
            name="Fallback School",
            slug="fallback-school",
            subdomain="fallback-school",
            is_active=False,
        )

        with patch(
            "apps.schools.tasks.provision_school_task.delay",
            side_effect=RuntimeError("broker offline"),
        ):
            result = dispatch_provision_school(str(school.id), contact_email="")

        school.refresh_from_db()
        self.assertTrue(result["fallback"])
        self.assertFalse(result["queued"])
        self.assertIsNone(result["job_id"])
        self.assertTrue(school.is_active)

    def test_complete_provisioning_syncs_when_queue_leaves_school_inactive(self):
        school = School.objects.create(
            name="Sync After Queue",
            slug="sync-after-queue",
            subdomain="sync-after-queue",
            is_active=False,
        )

        with patch(
            "apps.schools.tasks.provision_school_task.delay",
            return_value=type("R", (), {"id": "job-99"})(),
        ):
            with patch(
                "apps.schools.tasks.provision_school_sync",
                wraps=lambda sid, **kw: School.objects.filter(pk=sid).update(
                    is_active=True
                ),
            ) as sync:
                result = complete_provisioning_for_school(
                    str(school.id), contact_email="owner@example.com"
                )

        self.assertTrue(result["queued"])
        self.assertTrue(result["sync_completed"])
        sync.assert_called_once()
        school.refresh_from_db()
        self.assertTrue(school.is_active)
        self.assertTrue(result["is_active"])
