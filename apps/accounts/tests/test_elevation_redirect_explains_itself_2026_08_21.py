"""The tenant-host bounce used to say nothing at all.

``TenantHostControlPlaneIsolationMiddleware`` confines platform operators to the
signed impersonation flow. Land on a tenant host without a live session and it
redirects you to the manager host — silently. The operator clicked a tenant
link, arrived at /super/, and had nothing to read. Silence is worse than a wrong
message here, because the obvious inference is "I do not have permission", and
that is not what happened.

Nothing was denied. Direct operator access to a tenant's data is the least
observable path there is, so it is exchanged for an audited one. Root on Linux
is still logged by sudo; Administrator on Windows is still written to the
Security log. God-mode decides what you may do, never whether it is recorded.

The redirect now carries ``?elevate=<school_pk>``, because the manager host runs
on its own session cookie and a django.contrib.messages entry does not survive
the hop. Only the pk travels — no return path, so no redirect surface — and the
banner resolves the tenant's name from the database rather than from the query
string.
"""

from __future__ import annotations

import uuid
from urllib.parse import parse_qs, urlparse

from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings
from unittest.mock import patch

from apps.accounts.middleware import TenantHostControlPlaneIsolationMiddleware
from apps.accounts.models import User
from apps.schools.models import School
from apps.schools.templatetags.operator_elevation import (
    ELEVATE_PARAM,
    elevation_required_banner,
)


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@override_settings(ALLOWED_HOSTS=["*"])
class TheBounceCarriesItsReasonTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Tenant Alpha",
            slug=_unique("ta"),
            subdomain="tenant-alpha",
            is_active=True,
        )
        self.operator = User.objects.create_user(
            username=_unique("op"),
            password="testpass123",
            role=User.Role.SUPERADMIN,
            is_staff=True,
            is_superuser=False,
        )

    def _request(self, path="/portal/teacher/"):
        request = self.factory.get(path, HTTP_HOST="tenant-alpha.runmycampus.com")
        SessionMiddleware(lambda req: HttpResponse("ok")).process_request(request)
        request.session.save()
        request.user = self.operator
        request.school = self.school
        request.public_host_kind = None
        request.is_tenant_host = True
        return request

    def _redirect(self, request=None):
        middleware = TenantHostControlPlaneIsolationMiddleware(
            lambda req: HttpResponse("ok")
        )
        with patch.dict(
            "os.environ", {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            return middleware(request or self._request())

    def test_the_redirect_still_lands_on_the_manager_host(self):
        """The existing contract, unchanged — a query string is not a new route."""
        response = self._redirect()
        self.assertEqual(response.status_code, 302)
        loc = urlparse(response["Location"])
        self.assertEqual(loc.netloc, "manager.runmycampus.com")
        self.assertTrue((loc.path or "").rstrip("/").endswith("/super"))

    def test_it_names_the_tenant_it_came_from(self):
        response = self._redirect()
        query = parse_qs(urlparse(response["Location"]).query)
        self.assertEqual(query.get(ELEVATE_PARAM), [str(self.school.pk)])

    def test_it_carries_no_return_path(self):
        """A ``next`` here would be an open-redirect surface for nothing."""
        query = parse_qs(urlparse(self._redirect()["Location"]).query)
        self.assertNotIn("next", query)
        self.assertEqual(set(query) - {ELEVATE_PARAM}, set())

    def test_a_request_with_no_school_still_redirects_cleanly(self):
        request = self._request()
        request.school = None
        response = self._redirect(request)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("?", response["Location"])

    def test_an_operator_with_a_live_session_is_not_bounced_at_all(self):
        """The control is unchanged; only the explanation is new."""
        request = self._request()
        request.session["impersonation"] = {
            "school_id": str(self.school.id),
            "actor_id": self.operator.id,
        }
        request.session.save()
        response = self._redirect(request)
        self.assertEqual(response.status_code, 200)


class TheBannerExplainsItTests(TestCase):
    """The banner resolves the tenant itself. Query strings do not name tenants."""

    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Tenant Alpha",
            slug=_unique("ta"),
            subdomain=_unique("sd"),
            is_active=True,
        )

    def _context(self, query=""):
        request = self.factory.get(f"/super/{query}")
        return elevation_required_banner({"request": request})

    def test_nothing_renders_on_an_ordinary_visit(self):
        self.assertFalse(self._context()["show"])

    def test_it_renders_when_the_middleware_sent_the_operator_here(self):
        ctx = self._context(f"?{ELEVATE_PARAM}={self.school.pk}")
        self.assertTrue(ctx["show"])
        self.assertEqual(ctx["school"].pk, self.school.pk)

    def test_it_offers_the_audited_way_in(self):
        ctx = self._context(f"?{ELEVATE_PARAM}={self.school.pk}")
        self.assertTrue(ctx["picker_url"], "no link to start an audited session")

    def test_an_unknown_school_renders_nothing(self):
        """A well-formed pk that matches no row."""
        absent = uuid.uuid4()
        self.assertFalse(self._context(f"?{ELEVATE_PARAM}={absent}")["show"])

    def test_a_malformed_value_renders_nothing_rather_than_exploding(self):
        """School.pk is a UUID: junk raises ValidationError at the field layer."""
        for junk in ("../../etc/passwd", "999999999", "", "   ", "'; DROP TABLE"):
            with self.subTest(junk=junk):
                self.assertFalse(self._context(f"?{ELEVATE_PARAM}={junk}")["show"])

    def test_the_banner_never_renders_a_name_from_the_query_string(self):
        from pathlib import Path

        body = Path(
            "templates/schools/partials/_elevation_required_banner.html"
        ).read_text(encoding="utf-8")
        self.assertIn("school.name", body)
        self.assertNotIn("request.GET", body)

    def test_a_missing_request_is_survivable(self):
        self.assertFalse(elevation_required_banner({})["show"])
