from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.portal.views_support import support_help_hub
from apps.schools.models import School
from apps.siteconfig.models_feature_controls import GlobalSupportTicket

User = get_user_model()


class SupportHelpHubTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Hub School",
            slug="hub-school",
            subdomain="hub-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="hub-user",
            password="pass",
            is_staff=False,
        )

    def test_hub_renders_and_lists_user_tickets(self):
        GlobalSupportTicket.objects.create(
            school=self.school,
            user=self.user,
            subject="Lost password",
            body="Help",
        )
        request = self.factory.get("/portal/support/hub/")
        request.user = self.user
        request.school = self.school
        response = support_help_hub(request)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Lost password", content)
        self.assertIn("Knowledge base", content)
        # Portal shell: skip-link target + focusable main landmark (WCAG)
        self.assertIn('id="main-content"', content)
        self.assertIn('role="main"', content)
        self.assertIn('tabindex="-1"', content)
        self.assertIn('href="#main-content"', content)
        self.assertIn('data-page-archetype="support-hub"', content)
        self.assertIn('id="support-help-hub-heading"', content)
