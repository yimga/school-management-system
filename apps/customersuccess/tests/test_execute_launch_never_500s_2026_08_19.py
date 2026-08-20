"""The go-live button is the one control an activating school cannot route around.

Reported: a bare branded 500 on ``/siteconfig/guided-onboarding/execute-launch/``.

``execute_launch_view`` guarded only ``(AttributeError, DatabaseError, TypeError,
ValueError)``. The constant defined immediately below it in the same module —
``GUIDED_ONBOARDING_SOFT_FAILURES`` — adds ``KeyError``, so the codebase already knew a
``KeyError`` reaches these paths; the launch view simply never got it. Anything outside
that tuple became a 500 on the button that activation depends on, with no message, no log
reference, and nowhere to go.

The two properties asserted here are in tension and both matter:

  * NOTHING that ``execute_launch`` can raise may produce a 500 — the operator must always
    land back on a page they can act on, with a readable message and a reference.
  * ``AssertionError`` must STILL propagate. ``DatabaseOperationForbidden`` subclasses it
    precisely so that fail-soft guards cannot swallow a forbidden write, and a catch-all
    written without care would have quietly re-opened that hole.
"""
from __future__ import annotations

import uuid
from unittest import mock

from django.conf import settings
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership

_TARGET = "apps.customersuccess.views_tenant.execute_launch"

# The MFA ENROLMENT gate redirects a device-less principal to /mfa/setup/ before the view
# ever runs. Left in, every assertion below would pass on that redirect instead of on the
# view's own behaviour - green for the wrong reason, which is worse than red. Dropped so
# the VIEW is what answers; the redirect target is asserted explicitly for the same reason.
_MW = [
    m for m in settings.MIDDLEWARE
    if "RequireMFAMiddleware" not in m and "OperatorMfaRequiredMiddleware" not in m
]


@override_settings(MIDDLEWARE=_MW)
class ExecuteLaunchNeverFivehundredsTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Launch {uid}", slug=f"launch-{uid}",
            subdomain=f"launch{uid}", is_active=True,
        )
        self.admin = User.objects.create_superuser(
            username=f"launch_admin_{uid}", password="Test1234!x",
            email=f"l{uid}@test.com",
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role="ADMIN", is_primary=True
        )
        self.client.force_login(self.admin)
        session = self.client.session
        session["mfa_verified"] = True
        session["school_id"] = str(self.school.id)
        session.save()
        self.url = reverse("siteconfig:execute_launch")

    def _post(self):
        return self.client.post(
            self.url, {}, HTTP_HOST=f"{self.school.subdomain}.runmycampus.com"
        )

    def _messages(self, resp):
        return [str(m) for m in get_messages(resp.wsgi_request)]

    def _assert_landed_on_onboarding(self, resp):
        """Proves the redirect came from the VIEW, not from an auth gate in front of it."""
        self.assertEqual(resp.status_code, 302, "the go-live button must never 500")
        self.assertIn("guided-onboarding", resp["Location"])

    def test_a_key_error_is_reported_not_thrown(self):
        """The exact gap: KeyError was outside the guarded tuple."""
        with mock.patch(_TARGET, side_effect=KeyError("readiness")):
            resp = self._post()
        self._assert_landed_on_onboarding(resp)

    def test_a_validation_error_is_reported_not_thrown(self):
        with mock.patch(_TARGET, side_effect=ValidationError("not ready")):
            resp = self._post()
        self._assert_landed_on_onboarding(resp)

    def test_an_optional_integration_import_failure_is_reported_not_thrown(self):
        with mock.patch(_TARGET, side_effect=ImportError("no such optional backend")):
            resp = self._post()
        self._assert_landed_on_onboarding(resp)

    def test_the_operator_gets_a_message_carrying_a_reference(self):
        """A dead end with no reference is unreportable. The message must be actionable."""
        with mock.patch(_TARGET, side_effect=KeyError("readiness")):
            resp = self._post()
        joined = " ".join(self._messages(resp))
        self.assertIn("unexpected error", joined.lower())
        self.assertIn("reference", joined.lower())

    def test_a_soft_failure_keeps_its_own_retry_message(self):
        """The named, expected failures still say 'try again' rather than 'unexpected'."""
        with mock.patch(_TARGET, side_effect=ValueError("transient")):
            resp = self._post()
        self._assert_landed_on_onboarding(resp)
        joined = " ".join(self._messages(resp))
        self.assertIn("try again", joined.lower())
        self.assertNotIn("unexpected error", joined.lower())

    def test_an_assertion_error_still_propagates(self):
        """DatabaseOperationForbidden subclasses AssertionError so that fail-soft guards
        CANNOT swallow a forbidden write. A catch-all written without care re-opens that
        hole silently, which is why this assertion exists."""
        with mock.patch(_TARGET, side_effect=AssertionError("forbidden write")):
            with self.assertRaises(AssertionError):
                self.client.post(
                    self.url, {},
                    HTTP_HOST=f"{self.school.subdomain}.runmycampus.com",
                )

    def test_a_clean_launch_is_unaffected(self):
        with mock.patch(_TARGET, return_value={"ok": True, "errors": []}):
            resp = self._post()
        self.assertEqual(resp.status_code, 302)
        joined = " ".join(self._messages(resp))
        self.assertIn("live", joined.lower())
