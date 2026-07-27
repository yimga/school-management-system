"""The MFA trusted-browser opt-in must be driven by the trust-PERIOD control.

Old bug: the login MFA page had a "days to trust" dropdown that was DECOUPLED from
a separate "remember this device" checkbox. A user who changed the day count but
did not tick the checkbox armed nothing, so the next login re-prompted for MFA —
the "I set the days but it still asks me" complaint. The period control is now the
switch: picking a real allowed period opts in; "Don't trust" (0) does not; the
legacy checkbox flag is still honored for back-compat.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.accounts.mfa_device_trust import device_trust_allowed_days, device_trust_opt_in


class DeviceTrustOptInTests(SimpleTestCase):
    def test_picking_a_real_period_arms_trust_without_a_checkbox(self):
        allowed = device_trust_allowed_days()
        self.assertTrue(device_trust_opt_in(trust_days_value=str(allowed[0])))
        self.assertTrue(device_trust_opt_in(trust_days_value=allowed[-1]))

    def test_dont_trust_sentinel_does_not_opt_in(self):
        self.assertFalse(device_trust_opt_in(trust_days_value="0"))
        self.assertFalse(device_trust_opt_in(trust_days_value=""))
        self.assertFalse(device_trust_opt_in(trust_days_value=None))

    def test_out_of_range_period_does_not_opt_in(self):
        # A value not in the allowed set (e.g. a hand-crafted 999) must not opt in.
        self.assertFalse(device_trust_opt_in(trust_days_value="999"))

    def test_legacy_checkbox_flag_still_honored(self):
        self.assertTrue(device_trust_opt_in(remember_flag="1", trust_days_value="0"))
        self.assertTrue(device_trust_opt_in(remember_flag=True, trust_days_value=None))

    def test_nothing_submitted_does_not_opt_in(self):
        self.assertFalse(device_trust_opt_in())
