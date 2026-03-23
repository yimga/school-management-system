"""Operator policy page — manager host / super."""

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User


@override_settings(ALLOWED_HOSTS=["*"])
class SuperOperatorPolicyViewTests(TestCase):
    def test_operator_policy_200_manager_host(self):
        user = User.objects.create_user(
            username="op_policy_su",
            password="x",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(user)
        url = reverse("super:operator_policy")
        r = self.client.get(url, HTTP_HOST="manager.runmycampus.com")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Operator policy", html=False)
        self.assertContains(r, "bridge-manifest", html=False)
