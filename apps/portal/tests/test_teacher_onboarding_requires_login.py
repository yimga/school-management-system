"""Seal: teacher onboarding requires login on BOTH the default and legacy paths.

Same class of finding as student onboarding: the default path redirects to the
`@login_required` Unified engine wizard, but the `?legacy=1` opt-out (whose stale
docstring said "Allows unauthenticated users to register") could CREATE a User
(role=TEACHER) + TeacherProfile for an ANONYMOUS visitor — an unauthenticated
account-creation endpoint. No COPPA angle (teachers are adults), but the same
auth-bypass / staff-directory-pollution vector. `@login_required` on the view
holds the legacy branch to the same auth bar as the engine path.

`test_anonymous_legacy_path_requires_login` is the must-fire seal.
"""

import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from apps.schools.models import School, SchoolMembership


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class TeacherOnboardingRequiresLoginTests(TestCase):
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
            name="Seal School T", slug="seal-sch-t", subdomain="seal-sch-t", is_active=True
        )

    def tearDown(self):
        self.env.stop()

    def _get(self, path):
        return self.client.get(path, HTTP_HOST="seal-sch-t.runmycampus.com")

    def test_anonymous_default_path_requires_login(self):
        r = self._get("/portal/teacher/onboarding/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/authentication/login/", r["Location"])

    def test_anonymous_legacy_path_requires_login(self):
        # Must-fire: the ?legacy=1 opt-out was anonymously reachable and could
        # create a teacher User + profile before @login_required.
        r = self._get("/portal/teacher/onboarding/?legacy=1")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/authentication/login/", r["Location"])

    def test_authenticated_member_is_not_login_gated(self):
        User = get_user_model()
        member = User.objects.create_user(
            username="seal_member_t", email="seal_member_t@example.com", password="pwd123456"
        )
        SchoolMembership.objects.create(school=self.school, user=member)
        self.client.force_login(member)
        r = self._get("/portal/teacher/onboarding/?legacy=1")
        location = r.get("Location") or ""
        self.assertNotIn(
            "/authentication/login/",
            location,
            "A school member must not be bounced to login by the onboarding gate.",
        )
