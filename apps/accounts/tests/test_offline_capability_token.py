from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models_offline_device import DeviceRegistration, OfflineCapabilityToken
from apps.schools.models import School


class OfflineCapabilityTokenTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(name="Device School", slug="device-school")
        self.user = User.objects.create_user(username="teacher_dev", password="Test1234!")
        self.device = DeviceRegistration.objects.create(
            school=self.school,
            user=self.user,
            device_id="tablet-001",
            permission_bitmap=["attendance.mark"],
        )

    def test_token_expiry(self):
        token = OfflineCapabilityToken.objects.create(
            device=self.device,
            school=self.school,
            user=self.user,
            token_fingerprint="abc123",
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.assertFalse(token.is_valid)

    def test_active_device(self):
        self.assertTrue(self.device.is_active)
