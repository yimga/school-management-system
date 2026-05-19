"""Tenant API guards — school_id param membership."""

import uuid

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.schools.models import School, SchoolMembership
from apps.schools.tenant_api_guards import resolve_school_from_request_param


class TenantApiGuardsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        uid = uuid.uuid4().hex[:8]
        cls.school_a = School.objects.create(
            name=f"Guard A {uid}",
            slug=f"ga-{uid}",
            subdomain=f"ga{uid}",
            is_active=True,
        )
        cls.school_b = School.objects.create(
            name=f"Guard B {uid}",
            slug=f"gb-{uid}",
            subdomain=f"gb{uid}",
            is_active=True,
        )
        User = get_user_model()
        cls.user = User.objects.create_user(
            username=f"guard_u_{uid}", password="Test1234", role="ADMIN"
        )
        SchoolMembership.objects.create(
            user=cls.user, school=cls.school_a, role="ADMIN", is_primary=True
        )

    def setUp(self):
        self.factory = RequestFactory()

    def test_foreign_school_id_forbidden(self):
        req = self.factory.get(f"/?school_id={self.school_b.pk}")
        req.user = self.user
        req.school = self.school_a
        school, deny = resolve_school_from_request_param(req)
        self.assertIsNone(school)
        self.assertIsNotNone(deny)
        self.assertEqual(deny.status_code, 403)

    def test_own_school_id_allowed(self):
        req = self.factory.get(f"/?school_id={self.school_a.pk}")
        req.user = self.user
        req.school = self.school_a
        school, deny = resolve_school_from_request_param(req)
        self.assertIsNotNone(school)
        self.assertIsNone(deny)
