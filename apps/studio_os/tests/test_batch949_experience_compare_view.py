"""
PATH §6.6 III.11 / SOT §11.4 batch 949 — Studio OS Experience compare subpage (before/after).

Pairs with ``studio_rollback`` (``test_experience_rollback``) and ``get_studio_compare_context``.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Permission

User = get_user_model()


class Batch949ExperienceCompareViewTests(TestCase):
    def setUp(self):
        self.compare_url = reverse("studio_os:experience_compare")
        self.user = User.objects.create_user(
            username="batch949-compare",
            email="batch949-compare@example.com",
            password="password",
            role=User.Role.IT_ADMIN,
        )
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        manage_perm, _ = Permission.objects.get_or_create(
            code="settings.manage",
            defaults={"name": "Manage settings"},
        )
        self.user.feature_permissions.add(manage_perm)

    def test_experience_compare_get_ok_for_studio_user(self):
        self.client.login(username=self.user.username, password="password")
        response = self.client.get(self.compare_url)
        self.assertEqual(response.status_code, 200)
        # Subpage partial + shell embed title (before/after list uses {% for e in before_entries %})
        self.assertContains(response, "studio-os-subpage-canvas", html=False)
        self.assertContains(response, "Compare", html=False)
