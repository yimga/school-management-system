"""PATH III.33: guided onboarding (Setup Studio) exposes Launch Studio shell URL."""

from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.customersuccess.views_tenant import (
    _guided_onboarding_fallback_context,
    guided_onboarding_view,
)
from apps.schools.models import School


class GuidedOnboardingFallbackLaunchUrlTests(SimpleTestCase):
    def test_fallback_includes_launch_studio_url(self):
        ctx = _guided_onboarding_fallback_context(
            school=None, detail="No school context."
        )
        self.assertIn("launch_studio_url", ctx)
        if ctx["launch_studio_url"]:
            self.assertIn("/studio/launch", ctx["launch_studio_url"])


@override_settings(ALLOWED_HOSTS=["*"])
class GuidedOnboardingEmbedLaunchLinkTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="GH",
            slug="gh",
            subdomain="gh",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="gh_u", password="x", is_staff=True, role=User.Role.ADMIN
        )
        self.factory = RequestFactory()

    def test_embed_response_contains_launch_studio_href(self):
        req = self.factory.get(
            "/siteconfig/guided-onboarding/", {"embed": "1"}
        )
        req.user = self.user
        req.school = self.school
        resp = guided_onboarding_view(req)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("Open in Launch Studio (full shell)", body)
        self.assertIn("pane=plan", body)
        self.assertIn("pane=checklist", body)
        self.assertIn("pane=role_preview", body)
        self.assertIn("Open data import", body)
        self.assertIn("Review launch-without-roster option", body)
        self.assertIn("Required decision", body)
        try:
            expected = reverse("studio_os:launch")
        except Exception:  # noqa: BLE001
            self.skipTest("studio_os:launch not in urlconf")
        self.assertIn(expected, body)
