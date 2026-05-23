"""SODP batch 1418 — provision.signup apply path registers DeviceRegistration."""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.accounts.models import User
from apps.accounts.models_offline_device import DeviceRegistration
from apps.platform_runtime.offline_queue import _apply_provision_signup
from apps.schools.models import School, SchoolMembership


class OfflineProvisionSignupApplyTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Provision {uid}",
            slug=f"prov-{uid}",
            subdomain=f"prov{uid}",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            username=f"prov_t_{uid}",
            password="pass-test",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.get_or_create(
            user=self.teacher,
            school=self.school,
            defaults={"role": self.teacher.role, "is_primary": True},
        )

    def test_registers_device_on_first_apply(self):
        result = _apply_provision_signup(
            self.school.pk,
            self.teacher.pk,
            {"device_id": "tablet-field-001"},
        )
        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("created"))
        reg = DeviceRegistration.objects.get(
            school=self.school,
            user=self.teacher,
            device_id="tablet-field-001",
        )
        self.assertIsNone(reg.revoked_at)

    def test_dedups_on_repeat_apply(self):
        _apply_provision_signup(
            self.school.pk,
            self.teacher.pk,
            {"device_id": "tablet-field-002", "public_key_fingerprint": "abc123"},
        )
        result = _apply_provision_signup(
            self.school.pk,
            self.teacher.pk,
            {"device_id": "tablet-field-002", "public_key_fingerprint": "def456"},
        )
        self.assertTrue(result.get("ok"))
        self.assertFalse(result.get("created"))
        self.assertEqual(
            DeviceRegistration.objects.filter(
                school=self.school,
                user=self.teacher,
                device_id="tablet-field-002",
            ).count(),
            1,
        )
