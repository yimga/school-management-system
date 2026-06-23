"""Pluggable provider-cancel adapter for offboarding (O4).

The remote subscription cancel is resolved from configuration so an operator can
wire a real Stripe client without a code change, while the default stays a safe
no-op (ref recorded ``remote_pending``). These are pure SimpleTestCases — the
resolution + guard logic needs no database.
"""
from __future__ import annotations

import os
from unittest import mock

from django.test import SimpleTestCase, override_settings

from apps.billing import remote_cancel

# Module-level callables referenced by dotted path in the tests below.
_CALLS: list = []


def _adapter_true(ref: str) -> bool:
    _CALLS.append(ref)
    return True


def _adapter_false(ref: str) -> bool:
    _CALLS.append(ref)
    return False


def _adapter_boom(ref: str) -> bool:
    raise RuntimeError("provider exploded")


def _adapter_truthy_nonbool(ref: str):
    return "confirmed"  # not a bool -> must be coerced via bool()


_NOT_CALLABLE = "i am a string, not a function"

_PFX = "apps.billing.tests.test_remote_cancel_adapter"


class RemoteCancelAdapterTests(SimpleTestCase):
    def setUp(self):
        _CALLS.clear()

    @override_settings(BILLING_REMOTE_CANCEL_ADAPTER=None)
    def test_default_no_adapter_is_safe_noop(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RMC_BILLING_REMOTE_CANCEL_ADAPTER", None)
            self.assertIsNone(remote_cancel.resolve_remote_cancel_adapter())
            self.assertFalse(remote_cancel.try_remote_cancel("sub_123"))

    def test_empty_ref_short_circuits_before_adapter(self):
        # Even with a raising adapter configured, an empty ref returns False
        # without ever resolving/calling it.
        with override_settings(BILLING_REMOTE_CANCEL_ADAPTER=f"{_PFX}._adapter_boom"):
            self.assertFalse(remote_cancel.try_remote_cancel(""))

    @override_settings(BILLING_REMOTE_CANCEL_ADAPTER=None)
    def test_setting_adapter_returning_true(self):
        with override_settings(BILLING_REMOTE_CANCEL_ADAPTER=f"{_PFX}._adapter_true"):
            self.assertTrue(remote_cancel.try_remote_cancel("sub_a"))
        self.assertEqual(_CALLS, ["sub_a"])

    def test_setting_adapter_returning_false(self):
        with override_settings(BILLING_REMOTE_CANCEL_ADAPTER=f"{_PFX}._adapter_false"):
            self.assertFalse(remote_cancel.try_remote_cancel("sub_b"))
        self.assertEqual(_CALLS, ["sub_b"])

    def test_adapter_result_is_coerced_to_bool(self):
        with override_settings(
            BILLING_REMOTE_CANCEL_ADAPTER=f"{_PFX}._adapter_truthy_nonbool"
        ):
            result = remote_cancel.try_remote_cancel("sub_c")
        self.assertIs(result, True)

    def test_adapter_raising_is_guarded_to_false(self):
        with override_settings(BILLING_REMOTE_CANCEL_ADAPTER=f"{_PFX}._adapter_boom"):
            self.assertFalse(remote_cancel.try_remote_cancel("sub_d"))

    def test_bad_dotted_path_falls_back_to_noop(self):
        with override_settings(
            BILLING_REMOTE_CANCEL_ADAPTER="apps.billing.nope.does_not_exist"
        ):
            self.assertIsNone(remote_cancel.resolve_remote_cancel_adapter())
            self.assertFalse(remote_cancel.try_remote_cancel("sub_e"))

    def test_non_callable_target_falls_back_to_noop(self):
        with override_settings(BILLING_REMOTE_CANCEL_ADAPTER=f"{_PFX}._NOT_CALLABLE"):
            self.assertIsNone(remote_cancel.resolve_remote_cancel_adapter())
            self.assertFalse(remote_cancel.try_remote_cancel("sub_f"))

    @override_settings(BILLING_REMOTE_CANCEL_ADAPTER=None)
    def test_env_var_used_when_setting_absent(self):
        with mock.patch.dict(
            os.environ,
            {"RMC_BILLING_REMOTE_CANCEL_ADAPTER": f"{_PFX}._adapter_true"},
        ):
            self.assertTrue(remote_cancel.try_remote_cancel("sub_g"))
        self.assertEqual(_CALLS, ["sub_g"])

    def test_setting_takes_precedence_over_env(self):
        with override_settings(
            BILLING_REMOTE_CANCEL_ADAPTER=f"{_PFX}._adapter_true"
        ), mock.patch.dict(
            os.environ,
            {"RMC_BILLING_REMOTE_CANCEL_ADAPTER": f"{_PFX}._adapter_false"},
        ):
            self.assertTrue(remote_cancel.try_remote_cancel("sub_h"))
        self.assertEqual(_CALLS, ["sub_h"])

    def test_offboarding_seam_delegates_to_adapter(self):
        # The offboarding module's private seam must route through the adapter.
        from apps.billing import offboarding

        with override_settings(BILLING_REMOTE_CANCEL_ADAPTER=f"{_PFX}._adapter_true"):
            self.assertTrue(offboarding._try_remote_cancel("sub_i"))
        self.assertEqual(_CALLS, ["sub_i"])
