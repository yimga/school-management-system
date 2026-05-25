from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.portal.views_support import support_help_hub

User = get_user_model()


class SupportHelpHubTests(TestCase):
    def test_legacy_hub_redirects_to_unified_help_center(self):
        request = RequestFactory().get("/portal/support/hub/?section=support")
        request.user = User.objects.create_user(
            username="hub-user",
            password="pass",
            is_staff=False,
        )
        response = support_help_hub(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/help/", response.url)
        self.assertIn("section=support", response.url)
