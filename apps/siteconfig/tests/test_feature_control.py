"""Tests for Feature Control Panel."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

User = get_user_model()


class FeatureControlPanelTest(TestCase):
    """Test Feature Control Panel view."""

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            username="super", email="super@test.com", password="testpass123"
        )
        self.staff_user = User.objects.create_user(
            username="staff", email="staff@test.com", password="testpass123", is_staff=True
        )
        self.client = Client()

    def test_superuser_can_access(self):
        """Superuser can access Feature Control Panel."""
        self.client.login(username="super", password="testpass123")
        url = reverse("siteconfig:feature_control_panel")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Feature Control Panel", response.content)
        self.assertIn(b"Save changes", response.content)

    def test_user_without_permission_forbidden(self):
        """User without settings.feature_control receives 403."""
        self.client.login(username="staff", password="testpass123")
        url = reverse("siteconfig:feature_control_panel")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_user_with_permission_can_access(self):
        """User with settings.feature_control permission can access."""
        from apps.accounts.models import AccessRole, Permission

        perm = Permission.objects.get(code="settings.feature_control")
        role, _ = AccessRole.objects.get_or_create(
            code="IT_ADMIN", defaults={"name": "IT Admin", "description": ""}
        )
        role.permissions.add(perm)
        self.staff_user.role = "IT_ADMIN"
        self.staff_user.roles.add(role)
        self.staff_user.save()

        self.client.login(username="staff", password="testpass123")
        url = reverse("siteconfig:feature_control_panel")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Feature Control Panel", response.content)

    def test_anonymous_redirected_to_login(self):
        """Anonymous user redirected to login."""
        url = reverse("siteconfig:feature_control_panel")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"].lower())
