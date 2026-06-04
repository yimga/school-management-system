"""BOLA/IDOR guards for campus school switching."""

import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.schools.models import School, SchoolMembership
from apps.schools.tenant_switch_security import (
    schools_user_may_operate_on,
    user_may_access_school_api,
    user_may_switch_to_school,
)


class TenantSwitchSecurityTests(TestCase):
    def setUp(self):
        # Pin the control-plane operator allowlist to its SUPERADMIN-only default
        # so these BOLA/IDOR assertions are env-independent. Without this a local
        # ``.env.local`` setting CONTROL_PLANE_OPERATOR_ROLES=SUPERADMIN,ADMIN would
        # promote the tenant ADMIN below to a platform operator and silently flip
        # the cross-tenant "denied" assertions (the test must verify default config,
        # not whatever a developer's shell happens to export).
        _env_patch = mock.patch.dict(
            os.environ, {"CONTROL_PLANE_OPERATOR_ROLES": "SUPERADMIN"}
        )
        _env_patch.start()
        self.addCleanup(_env_patch.stop)
        User = get_user_model()
        self.parent = School.objects.create(
            name="District",
            slug="district",
            subdomain="district",
            is_active=True,
        )
        self.child = School.objects.create(
            name="Campus A",
            slug="campus-a",
            subdomain="campus-a",
            parent_school=self.parent,
            is_active=True,
        )
        self.other = School.objects.create(
            name="Other District",
            slug="other-district",
            subdomain="other-district",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username="district_admin",
            password="Test1234",
            role="ADMIN",
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.parent, role="ADMIN", is_primary=True
        )

    def test_parent_member_may_enter_child_campus(self):
        self.assertTrue(
            user_may_switch_to_school(
                self.admin, self.child, active_school=self.parent
            )
        )

    def test_parent_member_cannot_enter_unrelated_school(self):
        self.assertFalse(
            user_may_switch_to_school(
                self.admin, self.other, active_school=self.parent
            )
        )

    def test_api_access_child_via_parent_membership(self):
        self.assertTrue(
            user_may_access_school_api(
                self.admin,
                self.child,
                session_school_id=str(self.parent.pk),
            )
        )

    def test_api_access_denied_unrelated_school(self):
        self.assertFalse(user_may_access_school_api(self.admin, self.other))

    def test_api_access_direct_membership(self):
        self.assertTrue(user_may_access_school_api(self.admin, self.parent))

    def test_schools_user_may_operate_on_includes_child_campus(self):
        allowed = schools_user_may_operate_on(
            self.admin, active_school=self.parent
        )
        allowed_ids = {s.pk for s in allowed}
        self.assertIn(self.parent.pk, allowed_ids)
        self.assertIn(self.child.pk, allowed_ids)
        self.assertNotIn(self.other.pk, allowed_ids)
