"""Operator Help Center hub + KB control-plane shell."""



from django.contrib.auth import get_user_model

from django.test import Client, SimpleTestCase, TestCase, override_settings

from django.urls import reverse



from apps.portal.models_kb import HelpAudience, KBArticle, KBCategory

from apps.schools.middleware import MANAGER_HOST_ALLOWED_PREFIXES





def _ensure_operator_kb_article(author) -> None:

    category, _ = KBCategory.objects.get_or_create(

        slug="getting-started",

        defaults={

            "name": "Getting Started",

            "description": "Operator test category",

            "icon": "fa-rocket",

            "display_order": 1,

            "is_active": True,

        },

    )

    KBArticle.objects.update_or_create(

        slug="setting-up-school-info",

        defaults={

            "title": "Setting up school info",

            "category": category,

            "summary": "Operator help center regression article.",

            "content": "Body for operator KB shell test.",

            "status": "PUBLISHED",

            "author": author,

            "help_audience": HelpAudience.OPERATOR,

            "is_global_article": True,

        },

    )





@override_settings(ALLOWED_HOSTS=["*", "manager.runmycampus.com", "testserver"])

class OperatorHelpCenterHttpTests(TestCase):

    host = "manager.runmycampus.com"



    @classmethod

    def setUpTestData(cls):

        User = get_user_model()

        cls.superuser = User.objects.filter(is_superuser=True).first()

        if cls.superuser is None:

            cls.superuser = User.objects.create_superuser(

                username="help_center_audit",

                email="help@example.com",

                password="AuditTest_1234",

            )

        _ensure_operator_kb_article(cls.superuser)



    def setUp(self):

        self.client = Client()

    def _login(self):
        # Operators on the manager host need a confirmed MFA device AND a
        # manager-session-bound, MFA-verified login (the manager host reads
        # MANAGER_SESSION_COOKIE_NAME, a separate cookie); a bare force_login
        # writes only the default cookie with no MFA, so RequireMFAMiddleware
        # 302s the request to /authentication/mfa/setup/. The shared helper arms
        # all three — the real state of a logged-in operator.
        from apps.test_utils.http_clients import login_manager_client

        self.client = login_manager_client(
            self.superuser, password="AuditTest_1234", host=self.host
        )



    def test_help_center_renders_200(self):

        self._login()

        response = self.client.get("/help-center/", HTTP_HOST=self.host)

        self.assertEqual(response.status_code, 200)

        body = response.content.decode("utf-8", errors="replace")

        self.assertIn("Knowledge base", body)
        self.assertIn("rmc-help-center__metrics", body)
        self.assertIn("Discover", body)
        self.assertIn("data-rmc-help-search-input", body)



    def test_manager_help_redirects_to_help_center(self):

        self._login()

        response = self.client.get("/help/", HTTP_HOST=self.host)

        self.assertEqual(response.status_code, 302)

        self.assertIn("/help-center", response["Location"])



    def test_kb_home_uses_control_plane_chrome(self):

        self._login()

        response = self.client.get("/kb/", HTTP_HOST=self.host)

        self.assertEqual(response.status_code, 200)

        body = response.content.decode("utf-8", errors="replace")

        self.assertIn("rmc-kb-operator", body)

        self.assertIn("control-plane", body)



    def test_kb_article_renders_200(self):

        self._login()

        response = self.client.get(

            "/kb/article/setting-up-school-info/",

            HTTP_HOST=self.host,

        )

        self.assertEqual(response.status_code, 200)



    def test_feedback_loop_renders_200(self):

        self._login()

        response = self.client.get("/feedback-loop/", HTTP_HOST=self.host)

        self.assertEqual(response.status_code, 200)

    def test_feature_center_renders_200(self):
        self._login()
        response = self.client.get("/feature-center/", HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Request a capability", body)

    def test_contact_us_renders_200(self):
        self._login()
        response = self.client.get("/contact-us/", HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Contact us", response.content)

    def test_product_roadmap_renders_200(self):
        self._login()
        response = self.client.get("/product-roadmap/", HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Product roadmap", response.content)





@override_settings(ALLOWED_HOSTS=["*"])

class OperatorHelpCenterAllowlistTests(SimpleTestCase):

    def test_help_center_path_allowlisted(self):

        self.assertTrue(

            any(

                "/help-center/".startswith(prefix)

                for prefix in MANAGER_HOST_ALLOWED_PREFIXES

            )

        )

    def test_engagement_paths_allowlisted(self):
        for path in (
            "/feature-center/",
            "/contact-us/",
            "/product-roadmap/",
        ):
            self.assertTrue(
                any(path.startswith(prefix) for prefix in MANAGER_HOST_ALLOWED_PREFIXES),
                msg=path,
            )



    @override_settings(ROOT_URLCONF="config.manager_urls")

    def test_manager_help_center_reverse(self):

        path = reverse("manager_help_center")

        self.assertIn("/help-center", path)

