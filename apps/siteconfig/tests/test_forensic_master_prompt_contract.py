"""Forensic master prompt — contract tests for Section 8 hot paths."""

from __future__ import annotations

import json
import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.schools.models import School, SchoolMembership
from apps.schools.session_school_bind import sign_session_school_bind


_TENANT_SETTINGS = dict(
    ALLOWED_HOSTS=["*", "forensic-hub.runmycampus.com"],
    ROOT_URLCONF="config.tenant_urls",
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)


class ForensicThemeBuilderContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Forensic Hub School",
            slug="forensic-hub",
            subdomain="forensic-hub",
            is_active=True,
        )

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username=f"forensic_{uuid.uuid4().hex[:8]}",
            password="Test1234",
            email="forensic@example.com",
            role="ADMIN",
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role="ADMIN",
            is_primary=True,
        )
        self.client = Client(
            HTTP_HOST="forensic-hub.runmycampus.com",
            raise_request_exception=False,
        )
        self.client.force_login(self.user)

    @override_settings(**_TENANT_SETTINGS)
    def test_theme_hub_includes_builder_hero_marker(self):
        resp = self.client.get(reverse("siteconfig:theme_experience_hub"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "data-rmc-theme-hub-hero")

    @override_settings(**_TENANT_SETTINGS)
    def test_publish_api_accepts_layout_without_full_form_publish(self):
        url = reverse("siteconfig:theme_builder_publish_api")
        resp = self.client.post(
            url,
            data=json.dumps(
                {
                    "layout": {
                        "version": 1,
                        "surface": "light",
                        "blocks": [
                            {
                                "id": "hero",
                                "type": "hero",
                                "label": "Hero",
                                "enabled": True,
                            }
                        ],
                    },
                    "colors": {"primary_color": "#0d6efd"},
                    "publish": False,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("ok"))


class ForensicSessionBindMiddlewareTests(TestCase):
    def test_middleware_rejects_foreign_session_on_host(self):
        uid = uuid.uuid4().hex[:8]
        school_a = School.objects.create(
            name=f"Forensic A {uid}",
            slug=f"fa-{uid}",
            subdomain=f"fa{uid}",
            is_active=True,
        )
        school_b = School.objects.create(
            name=f"Forensic B {uid}",
            slug=f"fb-{uid}",
            subdomain=f"fb{uid}",
            is_active=True,
        )
        User = get_user_model()
        user = User.objects.create_user(
            username=f"forensic_bind_{uid}",
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
        sign_session_school_bind(
            session, school_id=str(school_a.pk), user_id=user.pk
        )
        session.save()
        resp = client.get("/authentication/backend/")
        self.assertIn(resp.status_code, (403, 302))
