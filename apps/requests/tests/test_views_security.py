import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.requests.models import AccessRequest
from apps.schools.models import School
from apps.test_utils.http_clients import login_tenant_admin_client


User = get_user_model()


class RequestsViewSecurityTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username="requests-staff",
            email="requests-staff@example.com",
            password="password",
        )
        self.staff.is_staff = True
        self.staff.role = getattr(
            User.Role, "IT_ADMIN", getattr(User.Role, "ADMIN", "ADMIN")
        )
        self.staff.save(update_fields=["is_staff", "role"])
        self.user = User.objects.create_user(
            username="requests-user",
            email="requests-user@example.com",
            password="password",
        )
        self.school_a = School.objects.create(
            name="School A",
            slug="school-a",
            subdomain="school-a",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="School B",
            slug="school-b",
            subdomain="school-b",
            is_active=True,
        )

    def test_requests_dashboard_handles_invalid_page_size(self):
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse("requests:dashboard"), {"page_size": "not-a-number"}
        )
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

    def test_requests_dashboard_scopes_to_active_school(self):
        AccessRequest.objects.create(
            request_type=AccessRequest.RequestType.MODULE_ACCESS,
            status=AccessRequest.Status.PENDING,
            requester=self.staff,
            title="School A request",
            school=self.school_a,
            schema_name="school-a",
        )
        AccessRequest.objects.create(
            request_type=AccessRequest.RequestType.MODULE_ACCESS,
            status=AccessRequest.Status.PENDING,
            requester=self.staff,
            title="School B request",
            school=self.school_b,
            schema_name="school-b",
        )
        # This ran as force_login(self.staff) and returned 302 to the APEX
        # /authentication/login/ -- the user read as anonymous on the tenant host,
        # because it holds no SchoolMembership for school-a. The sibling test above
        # passes only because it uses the default host, where that is not checked.
        # login_tenant_admin_client creates the membership AND arms MFA (this role
        # is on the baseline strict-MFA list, which is the next wall behind it).
        client = login_tenant_admin_client(
            self.staff,
            password="password",
            host="school-a.runmycampus.com",
            school=self.school_a,
        )
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            response = client.get(
                reverse("requests:dashboard"), HTTP_HOST="school-a.runmycampus.com"
            )
        # Name the redirect target on failure: a bare "302 != 200" here has read
        # as a scoping bug more than once when it was a gate redirect.
        self.assertEqual(
            response.status_code, 200, f"redirected to {getattr(response, 'url', '?')}"
        )
        rows = list(response.context["requests"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].school_id, self.school_a.id)
