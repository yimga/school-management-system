from django.test import Client, TestCase

from apps.accounts.models import User


class ViewsV1CsrfTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="csrf_api_user",
            password="testpass123",
            role=User.Role.ADMIN,
        )

    def test_finance_wallet_topup_requires_csrf_for_authenticated_browser_flow(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        valid_token = "a" * 32

        response = client.post(
            "/api/v1/finance/wallet/top-up",
            data='{"amount":"10.00"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

        client.cookies["csrftoken"] = valid_token
        response = client.post(
            "/api/v1/finance/wallet/top-up",
            data='{"amount":"10.00"}',
            content_type="application/json",
            HTTP_X_CSRFTOKEN=valid_token,
        )
        self.assertEqual(response.status_code, 400)

    def test_attendance_bulk_update_requires_csrf_for_authenticated_browser_flow(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        valid_token = "b" * 32

        response = client.patch(
            "/api/v1/attendance/bulk-update",
            data='{"records":[]}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)

        client.cookies["csrftoken"] = valid_token
        response = client.patch(
            "/api/v1/attendance/bulk-update",
            data='{"records":[]}',
            content_type="application/json",
            HTTP_X_CSRFTOKEN=valid_token,
        )
        self.assertEqual(response.status_code, 400)

    def test_enrollment_apply_alias_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)

        response = client.post(
            "/api/v1/enrollment/apply",
            data='{"school_slug":"demo-school","first_name":"Ada","last_name":"Lovelace","email":"ada@example.com"}',
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
