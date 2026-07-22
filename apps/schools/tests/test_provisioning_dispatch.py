from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.schools.models import School, SchoolMembership
from apps.schools.tasks import (
    complete_provisioning_for_school,
    dispatch_provision_school,
    ensure_admin_user_for_school,
)


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

    def test_complete_provisioning_defers_to_worker_when_queued(self):
        """Broker accepted the task — do not inline-migrate on the web path."""
        school = School.objects.create(
            name="Defer To Worker",
            slug="defer-to-worker",
            subdomain="defer-to-worker",
            is_active=False,
        )

        with patch(
            "apps.schools.tasks.provision_school_task.delay",
            return_value=type("R", (), {"id": "job-99"})(),
        ):
            with patch("apps.schools.tasks.provision_school_sync") as sync:
                result = complete_provisioning_for_school(
                    str(school.id), contact_email="owner@example.com"
                )

        self.assertTrue(result["queued"])
        self.assertFalse(result["fallback"])
        self.assertFalse(result["sync_completed"])
        self.assertTrue(result["sync_deferred_to_worker"])
        sync.assert_not_called()
        school.refresh_from_db()
        self.assertFalse(school.is_active)
        self.assertFalse(result["is_active"])

    def test_complete_provisioning_syncs_only_on_queue_fallback(self):
        school = School.objects.create(
            name="Fallback Sync School",
            slug="fallback-sync-school",
            subdomain="fallback-sync-school",
            is_active=False,
        )

        with patch(
            "apps.schools.tasks.provision_school_task.delay",
            side_effect=RuntimeError("broker offline"),
        ):
            result = complete_provisioning_for_school(
                str(school.id), contact_email="owner@example.com"
            )

        self.assertTrue(result["fallback"])
        self.assertTrue(result["sync_completed"])
        school.refresh_from_db()
        self.assertTrue(school.is_active)
        self.assertTrue(result["is_active"])

    def test_ensure_admin_user_promotes_new_school_to_primary(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="repeat@example.com",
            email="repeat@example.com",
            password="unused",
        )
        old = School.objects.create(
            name="NewBell School of Arts",
            slug="newbell-demo",
            subdomain="newbell-demo",
            is_active=False,
        )
        SchoolMembership.objects.create(
            user=user, school=old, role=User.Role.ADMIN, is_primary=True
        )
        new = School.objects.create(
            name="My Real School",
            slug="my-real-school",
            subdomain="my-real-school",
            is_active=False,
        )
        ensure_admin_user_for_school(new, "repeat@example.com")
        self.assertTrue(
            SchoolMembership.objects.filter(
                user=user, school=new, is_primary=True
            ).exists()
        )
        self.assertFalse(
            SchoolMembership.objects.filter(
                user=user, school=old, is_primary=True
            ).exists()
        )

    def test_ensure_admin_user_promotes_new_school_to_primary(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="repeat@example.com",
            email="repeat@example.com",
            password="unused",
        )
        old = School.objects.create(
            name="NewBell School of Arts",
            slug="newbell-demo",
            subdomain="newbell-demo",
            is_active=False,
        )
        SchoolMembership.objects.create(
            user=user, school=old, role=User.Role.ADMIN, is_primary=True
        )
        new = School.objects.create(
            name="My Real School",
            slug="my-real-school",
            subdomain="my-real-school",
            is_active=False,
        )
        ensure_admin_user_for_school(new, "repeat@example.com")
        self.assertTrue(
            SchoolMembership.objects.filter(
                user=user, school=new, is_primary=True
            ).exists()
        )
        self.assertFalse(
            SchoolMembership.objects.filter(
                user=user, school=old, is_primary=True
            ).exists()
        )
