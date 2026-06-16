"""pdp_enforce must fail CLOSED on a PDP error in enforce mode.

Regression: the except block logged a warning and returned the view (permit-by-
default), so any PDP error (DB loss, bad rule) silently granted access.
"""

from __future__ import annotations

from unittest import mock

from django.core.exceptions import PermissionDenied
from django.test import SimpleTestCase, override_settings

from apps.policies.enforcement import pdp_enforce

_PATCH = "apps.policies.enforcement.decide"


def _view(request, *a, **k):
    return "OK"


class _Req:
    user = None
    school = None


class _Decision:
    def __init__(self, allowed, reason="denied"):
        self.allowed = allowed
        self.reason = reason


@override_settings(POLICY_PDP_ENFORCEMENT_MODE="enforce")
class PdpEnforceModeTests(SimpleTestCase):
    def test_pdp_exception_denies(self):
        with mock.patch(_PATCH, side_effect=RuntimeError("pdp down")):
            wrapped = pdp_enforce(action="read", resource_kind="student")(_view)
            with self.assertRaises(PermissionDenied):
                wrapped(_Req())

    def test_allowed_decision_permits(self):
        with mock.patch(_PATCH, return_value=_Decision(True)):
            wrapped = pdp_enforce(action="read", resource_kind="student")(_view)
            self.assertEqual(wrapped(_Req()), "OK")

    def test_denied_decision_raises(self):
        with mock.patch(_PATCH, return_value=_Decision(False)):
            wrapped = pdp_enforce(action="read", resource_kind="student")(_view)
            with self.assertRaises(PermissionDenied):
                wrapped(_Req())


@override_settings(POLICY_PDP_ENFORCEMENT_MODE="advisory")
class PdpAdvisoryModeTests(SimpleTestCase):
    def test_pdp_exception_degrades_open_in_advisory(self):
        # advisory mode never blocks, even when the PDP errors.
        with mock.patch(_PATCH, side_effect=RuntimeError("pdp down")):
            wrapped = pdp_enforce(action="read", resource_kind="student")(_view)
            self.assertEqual(wrapped(_Req()), "OK")
