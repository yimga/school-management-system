from unittest.mock import patch

from django.test import TestCase

from apps.schools.models import School
from apps.schools.tasks import dispatch_provision_school


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
