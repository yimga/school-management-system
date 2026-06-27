"""No-DB precedence lock for the feature-flag arbiter (Wave D #11).

The audit flagged the feature-flag cascade as "diffuse — env flag + entitlement +
policy + plan, no single arbiter." Triage showed the paths actually AGREE because
they all bottom out in ``schools.models.is_feature_enabled`` (billing.entitlements.can
falls back to it; entitlement_gates.can_capability wraps billing.can). This test
pins ``is_feature_enabled``'s resolution PRECEDENCE so a future edit cannot silently
reorder it and make the layered resolvers disagree.

Only the branches that resolve WITHOUT a database query are asserted (billing
waiver, plan.included_features, addons, features JSON) — these all return True
before the tenant-modules / policy-fallback paths that need the DB. A full
cross-resolver parity test (is_feature_enabled vs billing.can vs can_capability)
is DB-backed and tracked as ciPending.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.schools.models import is_feature_enabled


class _StubPlan:
    def __init__(self, included_features):
        self.included_features = included_features


class _StubSchool:
    """Minimal duck-typed school — is_feature_enabled only does getattr()."""

    def __init__(self, *, billing_type=None, plan=None, addons=None, features=None):
        self.billing_type = billing_type
        self.plan = plan
        self.addons = addons
        self.features = features


class FeatureFlagPrecedenceLockTests(SimpleTestCase):
    def test_none_school_is_false(self):
        self.assertFalse(is_feature_enabled(None, "anything"))

    def test_billing_waiver_grants_any_feature(self):
        for waiver in ("COMPLIMENTARY", "MANUAL_OVERRIDE"):
            school = _StubSchool(billing_type=waiver)
            self.assertTrue(
                is_feature_enabled(school, "any_unlisted_capability"),
                f"{waiver} must grant full access",
            )

    def test_blank_code_is_false_when_not_waived(self):
        self.assertFalse(is_feature_enabled(_StubSchool(), ""))
        self.assertFalse(is_feature_enabled(_StubSchool(), "   "))

    def test_plan_included_features_grant(self):
        school = _StubSchool(plan=_StubPlan(["Gradebook", "sms_pack"]))
        # Case-insensitive + trimmed match.
        self.assertTrue(is_feature_enabled(school, "gradebook"))
        self.assertTrue(is_feature_enabled(school, " SMS_PACK "))

    def test_addons_grant(self):
        school = _StubSchool(addons=["library", "transport"])
        self.assertTrue(is_feature_enabled(school, "LIBRARY"))

    def test_features_json_truthy_grant(self):
        school = _StubSchool(features={"hostel": True, "canteen": False})
        self.assertTrue(is_feature_enabled(school, "hostel"))

    def test_waiver_takes_precedence_over_everything(self):
        # Even with no plan/addons/features, the waiver wins first.
        school = _StubSchool(billing_type="COMPLIMENTARY", plan=_StubPlan([]))
        self.assertTrue(is_feature_enabled(school, "premium_only_thing"))
