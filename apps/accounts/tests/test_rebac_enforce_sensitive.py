"""ReBAC enforcement when RMC_REBAC_ENFORCE_SENSITIVE is enabled."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.accounts.rebac import enforce_permission_token, write_tuple
from apps.accounts.rebac_sync import sync_membership_tuples
from apps.schools.models import School, SchoolMembership

User = get_user_model()


@override_settings(RMC_REBAC_ENFORCE_SENSITIVE=True, RMC_REBAC_ENABLED=True)
class RebacEnforceSensitiveTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="ReBAC School",
            slug=f"rbac-{uuid.uuid4().hex[:10]}",
            subdomain=f"rbac-{uuid.uuid4().hex[:10]}",
        )
        self.user = User.objects.create_user(
            username=f"u-{uuid.uuid4().hex[:8]}",
            email="rbac@test.local",
            password="x",
            role=User.Role.TEACHER,
        )
        membership = SchoolMembership.objects.create(
            school=self.school,
            user=self.user,
            role=User.Role.TEACHER,
        )
        sync_membership_tuples(membership)

    def test_enforce_denies_without_permission_tuple(self):
        with patch.object(self.user, "has_feature_permission", return_value=True):
            allowed = enforce_permission_token(
                self.user,
                "finance:invoice:view",
                school=self.school,
            )
        self.assertFalse(allowed)

    def test_enforce_allows_when_tuple_present(self):
        write_tuple(
            school=self.school,
            subject_type="user",
            subject_id=str(self.user.pk),
            relation="can",
            object_type="permission",
            object_id="finance:invoice:view",
            source="test",
        )
        with patch.object(self.user, "has_feature_permission", return_value=True):
            allowed = enforce_permission_token(
                self.user,
                "finance:invoice:view",
                school=self.school,
            )
        self.assertTrue(allowed)
