"""Auth checkpoint pages must not collapse inside portal chrome."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.schools.models import School, SchoolMembership


@override_settings(
    ALLOWED_HOSTS=["*"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    ROOT_URLCONF="config.tenant_urls",
)
class AuthCheckpointLayoutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Gilead Tech High",
            slug="gilead-tech",
            subdomain="gilead-tech",
            is_active=True,
        )
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="onboard-user",
            email="onboard@gilead.test",
            password="pass12345678",
            role=User.Role.TEACHER,
            profile_setup_completed=False,
            requires_password_change=False,
        )
        SchoolMembership.objects.create(
            user=cls.user,
            school=cls.school,
            role=User.Role.TEACHER,
            is_primary=True,
        )

    def _tenant_client(self, *, authenticated: bool = False) -> Client:
        client = Client(HTTP_HOST="gilead-tech.runmycampus.com")
        if authenticated:
            client.force_login(self.user)
            session = client.session
            session["school_id"] = str(self.school.pk)
            session["mfa_verified"] = True
            session.save()
        return client

    def test_magic_link_request_uses_checkpoint_not_portal_sidebar(self):
        response = self._tenant_client().get(reverse("accounts:magic_link_request"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('data-rmc-security-checkpoint-page="1"', html)
        self.assertIn('id="id_ml_email"', html)
        self.assertNotIn("portal-sidebar-col", html)
        self.assertNotIn("cpSearchInput", html)
        self.assertNotIn("Portal User", html)

    def test_join_school_uses_checkpoint_not_portal_sidebar(self):
        response = self._tenant_client().get(reverse("accounts:join_school"))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('data-rmc-security-checkpoint-page="1"', html)
        self.assertIn('id="id_code"', html)
        self.assertNotIn("portal-sidebar-col", html)

    def test_onboarding_profile_wraps_auth_shell_in_checkpoint(self):
        response = self._tenant_client(authenticated=True).get(
            reverse("accounts:onboarding_profile")
        )
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('data-rmc-security-checkpoint-page="1"', html)
        self.assertIn('id="onb-title"', html)
