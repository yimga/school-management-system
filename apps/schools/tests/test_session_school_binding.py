"""SessionSchoolBindingMiddleware — session school_id must match host campus."""

import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase

from apps.schools.models import School, SchoolMembership


class SessionSchoolBindingTests(TestCase):
    def test_foreign_session_school_logout_on_host_mismatch(self):
        uid = uuid.uuid4().hex[:8]
        school_a = School.objects.create(
            name=f"Bind A {uid}",
            slug=f"ba-{uid}",
            subdomain=f"ba{uid}",
            is_active=True,
        )
        school_b = School.objects.create(
            name=f"Bind B {uid}",
            slug=f"bb-{uid}",
            subdomain=f"bb{uid}",
            is_active=True,
        )
        User = get_user_model()
        user = User.objects.create_user(
            username=f"bind_{uid}",
            password="Test1234",
            role="ADMIN",
        )
        SchoolMembership.objects.create(
            user=user, school=school_a, role="ADMIN", is_primary=True
        )
        client = Client(HTTP_HOST=f"{school_b.subdomain}.runmycampus.com")
        client.force_login(user)
        session = client.session
        session["school_id"] = str(school_a.pk)
        session.save()
        resp = client.get("/authentication/backend/")
        # 403 specifically: the old `in (403, 302)` passed on the 302 that
        # TenantHostMembershipMiddleware emits further down the stack, which kept
        # this green while SessionSchoolBindingMiddleware was completely inert.
        self.assertEqual(resp.status_code, 403)
