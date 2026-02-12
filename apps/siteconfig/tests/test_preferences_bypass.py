"""Test that parents/teachers can access their own preferences (middleware bypass)."""
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User


class PreferencesBypassTests(TestCase):
    """Non-admin users can GET preferences page (module access bypass)."""

    def test_teacher_can_access_preferences(self):
        user = User.objects.create_user(username="teacher_pref", password="pass1234")
        user.role = User.Role.TEACHER
        user.save(update_fields=["role"])
        self.client.force_login(user)
        response = self.client.get(reverse("siteconfig:user_preferences"))
        self.assertEqual(response.status_code, 200)

    def test_parent_can_access_preferences(self):
        user = User.objects.create_user(username="parent_pref", password="pass1234")
        user.role = User.Role.PARENT
        user.save(update_fields=["role"])
        self.client.force_login(user)
        response = self.client.get(reverse("siteconfig:user_preferences"))
        self.assertEqual(response.status_code, 200)
