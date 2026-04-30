"""Post-signup activation gate and strict conversion lock integration."""

import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from apps.accounts.models import User
from apps.schools.activation_gate import (
    clear_activation_gate,
    school_activation_gate_pending,
    set_activation_gate_pending,
)
from apps.schools.models import School, SchoolMembership

User = get_user_model()


@override_settings(
    ALLOWED_HOSTS=["*"],
    SECURE_SSL_REDIRECT=False,
    DEBUG=True,
    ROOT_URLCONF="config.tenant_urls",
)
class ActivationGateIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=False)
        self.school = School.objects.create(
            name="Gate School",
            slug="gate-school",
            subdomain="gate-school",
            is_active=True,
            settings={},
        )
        set_activation_gate_pending(self.school)
        self.school.refresh_from_db()
        self.user = User.objects.create_user(
            username="gateadmin",
            email="gate@example.edu",
            password="Test1234!ab",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.get_or_create(
            user=self.user,
            school=self.school,
            defaults={"role": User.Role.ADMIN, "is_primary": True},
        )

    @patch.dict(
        os.environ,
        {"MULTI_TENANT_BASE_DOMAIN": "example.com"},
        clear=False,
    )
    @override_settings(MULTI_TENANT_BASE_DOMAIN="example.com")
    def test_portal_request_redirects_to_activation_landing(self):
        self.client.login(username="gateadmin", password="Test1234!ab")
        r = self.client.get(
            "/backend/",
            HTTP_HOST="gate-school.example.com",
            follow=False,
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn("/activation/first-action/", r["Location"])

    def test_clear_gate_helper(self):
        self.assertTrue(school_activation_gate_pending(self.school))
        clear_activation_gate(self.school)
        self.school.refresh_from_db()
        self.assertFalse(school_activation_gate_pending(self.school))

    @patch.dict(
        os.environ,
        {"MULTI_TENANT_BASE_DOMAIN": "example.com"},
        clear=False,
    )
    @override_settings(
        MULTI_TENANT_BASE_DOMAIN="example.com",
        CONVERSION_LOCK_STRICT=True,
    )
    def test_conversion_lock_redirects_non_allowlisted_route(self):
        """Strict conversion lock sends locked tenants to first-action until completion."""
        self.client.login(username="gateadmin", password="Test1234!ab")
        r = self.client.get(
            "/backend/",
            HTTP_HOST="gate-school.example.com",
            follow=False,
        )
        self.assertEqual(r.status_code, 302)
        self.assertIn("/activation/first-action/", r["Location"])
