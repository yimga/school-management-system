from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.requests.models import AccessRequest


User = get_user_model()


class RequestsViewSecurityTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="requests-staff",
            email="requests-staff@example.com",
            password="password",
        )
        self.staff.is_staff = True
        self.staff.role = getattr(User.Role, "IT_ADMIN", getattr(User.Role, "ADMIN", "ADMIN"))
        self.staff.save(update_fields=["is_staff", "role"])
        self.user = User.objects.create_user(
            username="requests-user",
            email="requests-user@example.com",
            password="password",
        )

    def test_requests_dashboard_handles_invalid_page_size(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse("requests:dashboard"), {"page_size": "not-a-number"})
        self.assertEqual(response.status_code, 200)

    def test_module_access_rejects_external_next_redirect(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("requests:module_access"),
            {
                "module": "finance",
                "action": "read",
                "next": "https://evil.example/phish",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("requests:dashboard"))
        self.assertEqual(AccessRequest.objects.count(), 1)
