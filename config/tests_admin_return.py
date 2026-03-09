"""Tests for admin return-to-origin (add_view redirect to next, safe URL)."""
from django.http import HttpResponseRedirect
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from django.contrib.auth.models import User


class AdminAddViewReturnToOriginTests(TestCase):
    """Test that add_view redirects to request.POST['next'] when safe."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin_return", email="a@test.com", password="password"
        )
        self.client.force_login(self.user)

    def test_add_page_with_next_includes_hidden_input(self):
        """GET add page with ?next= should render hidden input next in submit row."""
        changelist_url = reverse("admin:auth_user_changelist")
        url = reverse("admin:auth_user_add") + "?next=" + changelist_url
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'name="next"', response.content)
        self.assertIn(b'form="user_form"', response.content)

    def test_post_add_redirects_to_safe_next(self):
        """POST to add with valid data and next= same-origin URL redirects to next."""
        changelist_url = reverse("admin:auth_user_changelist")
        add_url = reverse("admin:auth_user_add")
        data = {
            "username": "newuser_return",
            "password1": "ComplexPass123!",
            "password2": "ComplexPass123!",
            "next": changelist_url,
            "_save": "Save",
        }
        response = self.client.post(add_url, data, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], changelist_url)
        User.objects.filter(username="newuser_return").delete()

    def test_post_add_ignores_external_next(self):
        """POST with next= external URL must not redirect to it (security)."""
        add_url = reverse("admin:auth_user_add")
        data = {
            "username": "newuser_ext",
            "password1": "ComplexPass123!",
            "password2": "ComplexPass123!",
            "next": "https://evil.example/phish",
            "_save": "Save",
        }
        response = self.client.post(add_url, data, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("evil.example", response["Location"])
        User.objects.filter(username="newuser_ext").delete()
