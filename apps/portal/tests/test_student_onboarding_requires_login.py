"""Seal: student onboarding requires login on BOTH the default and legacy paths.

Audit finding (proven by running): the default path redirects an anonymous
visitor to the Unified engine wizard, which is `@login_required`, so the surface
is school-mediated — but the `?legacy=1` opt-out rendered (HTTP 200) and could
CREATE a StudentProfile (+ a parent User + a guardian-invite email) for an
ANONYMOUS visitor, silently bypassing that gate. That also made the school-as-
agent COPPA basis dishonest (no school authorised an anonymous submission).
`@login_required` on the view holds the legacy branch to the same auth bar.

`test_anonymous_legacy_path_redirects_to_login` is the must-fire seal — the
legacy path returned 200 (rendered) before the decorator.
"""

import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from apps.schools.models import School, SchoolMembership


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class StudentOnboardingRequiresLoginTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()
        self.school = School.objects.create(
            name="Seal School", slug="seal-sch", subdomain="seal-sch", is_active=True
        )

    def tearDown(self):
        self.env.stop()

    def _get(self, path):
        return self.client.get(path, HTTP_HOST="seal-sch.runmycampus.com")

    def test_anonymous_default_path_redirects_to_login(self):
        r = self._get("/portal/student/onboarding/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/authentication/login/", r["Location"])

    def test_anonymous_legacy_path_redirects_to_login(self):
        # Must-fire: the ?legacy=1 opt-out rendered (200) for anonymous visitors
        # before @login_required, bypassing the gate the default path enforces.
        r = self._get("/portal/student/onboarding/?legacy=1")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/authentication/login/", r["Location"])

    def test_authenticated_member_is_not_login_gated(self):
        # The fix must not over-block a legitimate school member: they reach the
        # flow (render or engine redirect) rather than being bounced to login.
        User = get_user_model()
        member = User.objects.create_user(
            username="seal_member", email="seal_member@example.com", password="pwd123456"
        )
        SchoolMembership.objects.create(school=self.school, user=member)
        self.client.force_login(member)
        r = self._get("/portal/student/onboarding/?legacy=1")
        location = r.get("Location") or ""
        self.assertNotIn(
            "/authentication/login/",
            location,
            "A school member must not be bounced to login by the onboarding gate.",
        )
