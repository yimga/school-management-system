"""Provisioning seed gate — block husk operational navigation until Phase B."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from apps.schools.middleware_provisioning_seed_gate import ProvisioningSeedGateMiddleware
from apps.schools.models import School, SchoolMembership


@override_settings(
    ALLOWED_HOSTS=["*", "husk.runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    ROOT_URLCONF="config.tenant_urls",
)
class ProvisioningSeedGateMiddlewareTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="husk-owner@test.local",
            email="husk-owner@test.local",
            password="HuskPass123!",
            role=User.Role.ADMIN,
        )
        self.school = School.objects.create(
            name="Husk Gate School",
            slug="husk-gate",
            subdomain="husk-gate",
            is_active=True,
            settings={
                "provisioning": {
                    "phase_a_complete": True,
                    "phase_b_complete": False,
                }
            },
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        self.rf = RequestFactory()

    def _request(self, path: str, *, query_string: str = ""):
        request = self.rf.get(
            path,
            HTTP_HOST="husk-gate.runmycampus.com",
            HTTP_ACCEPT="text/html",
            HTTP_SEC_FETCH_DEST="document",
            QUERY_STRING=query_string,
        )
        request.user = self.user
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        request.school = self.school
        request.public_host_kind = "tenant"
        return request

    def test_redirects_backend_while_phase_b_incomplete(self):
        mw = ProvisioningSeedGateMiddleware(get_response=lambda r: HttpResponse("ok"))
        response = mw(self._request("/authentication/backend/"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/school/studio/provisioning", response["Location"])

    def test_allows_login_while_phase_b_incomplete(self):
        mw = ProvisioningSeedGateMiddleware(get_response=lambda r: HttpResponse("ok"))
        response = mw(self._request("/authentication/login/"))
        self.assertEqual(response.status_code, 200)

    def test_allows_provisioning_status_page(self):
        mw = ProvisioningSeedGateMiddleware(get_response=lambda r: HttpResponse("ok"))
        response = mw(self._request("/school/studio/provisioning/"))
        self.assertEqual(response.status_code, 200)

    def test_clears_when_phase_b_complete(self):
        self.school.settings = {
            "provisioning": {"phase_a_complete": True, "phase_b_complete": True}
        }
        self.school.save(update_fields=["settings"])
        mw = ProvisioningSeedGateMiddleware(get_response=lambda r: HttpResponse("ok"))
        response = mw(self._request("/authentication/backend/"))
        self.assertEqual(response.status_code, 200)

    def test_established_school_not_gated_when_workspace_probe_false(self):
        """Marker-less live schools must keep working even if the probe is wrong.

        After a failed/partial migrate_schemas, coverage-floor can yield
        ``tenant_workspace_exists is False`` for healthy tenants.
        ``provisioning_needs_resume`` then returns True — the seed gate must
        NOT follow that path or every post-login navigation is trapped.
        """
        self.school.settings = {}
        self.school.save(update_fields=["settings"])
        mw = ProvisioningSeedGateMiddleware(get_response=lambda r: HttpResponse("ok"))
        with patch(
            "apps.schools.provisioning_progress.provisioning_needs_resume",
            return_value=True,
        ):
            response = mw(self._request("/authentication/backend/"))
        self.assertEqual(response.status_code, 200)

    def test_redirect_does_not_forward_auto_query_string(self):
        mw = ProvisioningSeedGateMiddleware(get_response=lambda r: HttpResponse("ok"))
        response = mw(self._request("/authentication/backend/", query_string="auto=1"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/school/studio/provisioning", response["Location"])
        self.assertNotIn("auto=1", response["Location"])
