"""Welcome email URLs and HTML after school provisioning."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.schools.models import School
from apps.schools.provision_email_urls import (
    build_provision_setup_password_url,
    build_tenant_authentication_url,
)
from apps.schools.welcome_email import render_welcome_email_html


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com", DEBUG=False)
class WelcomeEmailProvisionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Mail Test School",
            slug="mail-test-school",
            subdomain="mail-test-school",
        )
        self.user = get_user_model().objects.create_user(
            username="principal_mail",
            email="principal@mailtest.test",
            password="unused",
        )
        self.user.set_unusable_password()
        self.user.save()

    def test_build_tenant_authentication_url_uses_subdomain(self):
        url = build_tenant_authentication_url(
            self.school, "/authentication/login/"
        )
        self.assertIn("mail-test-school.runmycampus.com", url)
        self.assertIn("/authentication/login/", url)

    def test_build_provision_setup_password_url_contains_legacy_setup(self):
        url = build_provision_setup_password_url(self.school, self.user)
        self.assertIn("mail-test-school.runmycampus.com", url)
        self.assertIn("/authentication/legacy-setup/", url)

    def test_render_welcome_email_includes_set_password_cta(self):
        setup = build_provision_setup_password_url(self.school, self.user)
        html = render_welcome_email_html(
            self.school,
            "principal@mailtest.test",
            setup_password_url=setup,
        )
        self.assertIn("Set your password", html)
        self.assertIn(setup, html)
