"""HTTP tests: me/switch-school rejects cross-tenant BOLA attempts."""

import json
import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.schools.models import School, SchoolMembership
from apps.schools.session_school_bind import sign_session_school_bind


class MeSwitchSchoolBOLATests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school_a = School.objects.create(
            name=f"School A {uid}",
            slug=f"a-{uid}",
            subdomain=f"a{uid}",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name=f"School B {uid}",
            slug=f"b-{uid}",
            subdomain=f"b{uid}",
            is_active=True,
        )
        User = get_user_model()
        self.user = User.objects.create_user(
            username=f"user_{uid}",
            password="Test1234",
            role="ADMIN",
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school_a,
            role="ADMIN",
            is_primary=True,
        )

    def test_switch_denied_for_non_member_school(self):
        host = f"{self.school_a.subdomain}.runmycampus.com"
        client = Client(HTTP_HOST=host)
        client.force_login(self.user)
        sign_session_school_bind(
            client.session, school_id=str(self.school_a.pk), user_id=self.user.pk
        )
        client.session.save()
        url = reverse("api_v1:me-switch-school")
        resp = client.post(
            url,
            data=json.dumps({"school_id": str(self.school_b.pk)}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_switch_allowed_for_member_school(self):
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school_b,
            role="ADMIN",
            is_primary=False,
        )
        host = f"{self.school_a.subdomain}.runmycampus.com"
        client = Client(HTTP_HOST=host)
        client.force_login(self.user)
        sign_session_school_bind(
            client.session, school_id=str(self.school_a.pk), user_id=self.user.pk
        )
        client.session.save()
        url = reverse("api_v1:me-switch-school")
        resp = client.post(
            url,
            data=json.dumps({"school_id": str(self.school_b.pk)}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)

    def test_parent_member_may_switch_to_child_without_child_membership(self):
        uid = uuid.uuid4().hex[:8]
        parent = School.objects.create(
            name=f"Parent {uid}",
            slug=f"p-{uid}",
            subdomain=f"p{uid}",
            is_active=True,
        )
        child = School.objects.create(
            name=f"Child {uid}",
            slug=f"c-{uid}",
            subdomain=f"c{uid}",
            parent_school=parent,
            is_active=True,
        )
        User = get_user_model()
        user = User.objects.create_user(
            username=f"district_{uid}",
            password="Test1234",
            role="ADMIN",
        )
        SchoolMembership.objects.create(
            user=user, school=parent, role="ADMIN", is_primary=True
        )
        host = f"{parent.subdomain}.runmycampus.com"
        client = Client(HTTP_HOST=host)
        client.force_login(user)
        sign_session_school_bind(
            client.session, school_id=str(parent.pk), user_id=user.pk
        )
        client.session.save()
        url = reverse("api_v1:me-switch-school")
        resp = client.post(
            url,
            data=json.dumps({"school_id": str(child.pk)}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200, resp.content.decode())
