from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.schools.models import School, SchoolMembership
from apps.schools.tasks import (
    complete_provisioning_for_school,
    dispatch_provision_school,
    ensure_admin_user_for_school,
)


class ProvisioningDispatchTests(TestCase):
    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_dispatch_uses_durable_outbox_never_sync_on_caller(self):
        school = School.objects.create(
            name="Fallback School",
            slug="fallback-school",
            subdomain="fallback-school",
            is_active=False,
        )
        fake_row = MagicMock()
        fake_row.pk = "11111111-1111-1111-1111-111111111111"

        with patch(
            "apps.platform_runtime.heavy_work_outbox.enqueue_provision_school",
            return_value=fake_row,
        ) as enq:
            with patch("apps.schools.tasks.provision_school_sync") as sync:
                result = dispatch_provision_school(str(school.id), contact_email="")

        enq.assert_called_once()
        sync.assert_not_called()
        self.assertTrue(result["queued"])
        self.assertTrue(result.get("durable_outbox"))
        self.assertEqual(result.get("outbox_id"), str(fake_row.pk))
        school.refresh_from_db()
        self.assertFalse(school.is_active)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_complete_provisioning_defers_to_outbox_when_queued(self):
        school = School.objects.create(
            name="Defer To Worker",
            slug="defer-to-worker",
            subdomain="defer-to-worker",
            is_active=False,
        )
        fake_row = MagicMock()
        fake_row.pk = "22222222-2222-2222-2222-222222222222"

        with patch(
            "apps.platform_runtime.heavy_work_outbox.enqueue_provision_school",
            return_value=fake_row,
        ):
            with patch("apps.schools.tasks.provision_school_sync") as sync:
                result = complete_provisioning_for_school(
                    str(school.id), contact_email="owner@example.com"
                )

        self.assertTrue(result["queued"])
        self.assertFalse(result["sync_completed"])
        self.assertTrue(result["sync_deferred_to_worker"])
        self.assertTrue(result.get("sync_deferred_to_durable_outbox"))
        sync.assert_not_called()
        school.refresh_from_db()
        self.assertFalse(school.is_active)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_eager_mode_uses_durable_outbox_not_caller_thread(self):
        school = School.objects.create(
            name="Eager Bg School",
            slug="eager-bg-school",
            subdomain="eager-bg-school",
            is_active=False,
        )
        fake_row = MagicMock()
        fake_row.pk = "33333333-3333-3333-3333-333333333333"

        with patch(
            "apps.platform_runtime.heavy_work_outbox.enqueue_provision_school",
            return_value=fake_row,
        ) as enq:
            with patch("apps.schools.tasks.provision_school_sync") as sync:
                result = dispatch_provision_school(
                    str(school.id), contact_email="owner@example.com"
                )

        enq.assert_called_once()
        sync.assert_not_called()
        self.assertTrue(result["queued"])
        self.assertTrue(result.get("eager_background"))
        self.assertTrue(result.get("durable_outbox"))

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_complete_provisioning_outbox_on_queue_path(self):
        school = School.objects.create(
            name="Fallback Sync School",
            slug="fallback-sync-school",
            subdomain="fallback-sync-school",
            is_active=False,
        )
        fake_row = MagicMock()
        fake_row.pk = "44444444-4444-4444-4444-444444444444"

        with patch(
            "apps.platform_runtime.heavy_work_outbox.enqueue_provision_school",
            return_value=fake_row,
        ):
            with patch("apps.schools.tasks.provision_school_sync") as sync:
                result = complete_provisioning_for_school(
                    str(school.id), contact_email="owner@example.com"
                )

        self.assertFalse(result["sync_completed"])
        self.assertTrue(result.get("durable_outbox") or result.get("sync_deferred_to_durable_outbox"))
        sync.assert_not_called()
        school.refresh_from_db()
        self.assertFalse(school.is_active)

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
