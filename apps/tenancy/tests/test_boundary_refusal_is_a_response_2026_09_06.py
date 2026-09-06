"""A tenant-boundary refusal must reach the caller as 403, not as a 500.

``boundary_core_guard`` raises ``SecurityIsolationException`` when a query
crosses the pinned tenant. Until 2026-09-06 nothing converted it into a
response: it was raised in that module, caught only inside that module and its
own tests, and reached Django's handler unhandled. The isolation worked -- the
query was refused -- but the platform then reported the refusal as a **500**.

Why the shape matters, and why this is a test rather than a tidy-up:

* a 500 reads as a platform bug, so a real refusal gets triaged as an outage
  and the security signal is lost among genuine errors;
* every blocked attempt pages whoever watches error monitoring, which is how
  alerting on exactly this signal gets muted;
* under DEBUG the error page renders a traceback of the guard itself;
* and an endpoint that answers 500 where its neighbours answer 403 tells a
  caller probing for cross-tenant access that they found something different.

It surfaced as two permanently-red tests in ``test_bola_idor_matrix.py``
(``switch-school`` and ``analytics-viz``), which reported
``SecurityIsolationException`` escaping the test client rather than a status
code -- for a control that was, all along, doing its job.
"""

from __future__ import annotations

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase

from apps.tenancy.exceptions import SecurityIsolationException
from apps.tenancy.middleware_boundary_guard import TenantBoundaryCoreGuardMiddleware


def _mw():
    return TenantBoundaryCoreGuardMiddleware(lambda request: HttpResponse("ok"))


class BoundaryRefusalIsAResponseTests(SimpleTestCase):
    def test_a_boundary_violation_becomes_403_json_on_an_api_path(self):
        request = RequestFactory().get("/api/v1/me/switch-school")
        response = _mw().process_exception(
            request, SecurityIsolationException("pinned=A got=B", detail="x")
        )
        self.assertIsNotNone(
            response,
            "the guard's own exception must not escape to the 500 handler",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_the_body_never_repeats_the_exception_message(self):
        """The message names the pinned school and the offending value.

        It belongs in the log, not in a response to the caller who just tried
        to cross the boundary.
        """
        secret = "pinned=school-A-uuid got=school-B-uuid"
        request = RequestFactory().get("/api/v1/anything")
        response = _mw().process_exception(
            request, SecurityIsolationException(secret, detail=secret)
        )
        body = response.content.decode()
        self.assertNotIn("school-A-uuid", body)
        self.assertNotIn("school-B-uuid", body)
        self.assertIn("tenant_boundary_violation", body)

    def test_a_browser_path_gets_a_plain_403_not_json(self):
        request = RequestFactory().get("/school/dashboard/")
        response = _mw().process_exception(
            request, SecurityIsolationException("nope")
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("application/json", response["Content-Type"])

    def test_an_unrelated_exception_is_left_alone(self):
        """The negative control.

        Returning a 403 for everything would convert unrelated crashes into
        silent denials -- a far worse bug than the one being fixed, and one
        that would make every other test in this file pass for free.
        """
        request = RequestFactory().get("/api/v1/anything")
        self.assertIsNone(
            _mw().process_exception(request, ValueError("something else")),
            "only a tenant-boundary refusal may be converted",
        )
