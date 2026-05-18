"""Declarative tenant override loader tests (E8)."""

from __future__ import annotations

from django.test import TestCase

from apps.policies.declarative_overrides import apply_overrides_dict
from apps.policies.models import TenantPolicyOverride
from apps.schools.models import School


class DeclarativeOverrideTests(TestCase):
    def setUp(self):
        self.s1 = School.objects.create(slug="m3do1", name="m3do1", subdomain="m3do1")
        self.s2 = School.objects.create(slug="m3do2", name="m3do2", subdomain="m3do2")

    def _payload(self, *entries):
        return {"version": 1, "overrides": list(entries)}

    def test_creates_new_rows(self):
        result = apply_overrides_dict(self._payload(
            {"school": "m3do1", "policy_key": "admissions.numbering", "value": {"prefix": "M3"}},
            {"school": "m3do2", "policy_key": "finance.late_fee_percent", "value": 5},
        ))
        self.assertEqual(result.created, 2)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.unchanged, 0)
        self.assertEqual(TenantPolicyOverride.objects.count(), 2)

    def test_idempotent_second_apply_unchanged(self):
        payload = self._payload(
            {"school": "m3do1", "policy_key": "k1", "value": {"x": 1}},
        )
        apply_overrides_dict(payload)
        result = apply_overrides_dict(payload)
        self.assertEqual(result.unchanged, 1)
        self.assertEqual(result.created, 0)
        self.assertEqual(result.updated, 0)

    def test_value_change_triggers_update(self):
        apply_overrides_dict(self._payload(
            {"school": "m3do1", "policy_key": "k1", "value": {"x": 1}},
        ))
        result = apply_overrides_dict(self._payload(
            {"school": "m3do1", "policy_key": "k1", "value": {"x": 2}},
        ))
        self.assertEqual(result.updated, 1)
        existing = TenantPolicyOverride.objects.get(school=self.s1, policy_key="k1")
        self.assertEqual(existing.value, {"x": 2})

    def test_unknown_school_recorded_as_error(self):
        result = apply_overrides_dict(self._payload(
            {"school": "no-such-school", "policy_key": "k", "value": 1},
        ))
        self.assertTrue(any("no-such-school" in e for e in (result.errors or [])))
        self.assertEqual(result.created, 0)

    def test_prune_removes_unlisted(self):
        TenantPolicyOverride.objects.create(school=self.s1, policy_key="keep", value=1)
        TenantPolicyOverride.objects.create(school=self.s1, policy_key="zap", value=2)
        result = apply_overrides_dict(
            self._payload({"school": "m3do1", "policy_key": "keep", "value": 1}),
            prune=True,
        )
        self.assertEqual(result.pruned, 1)
        self.assertFalse(
            TenantPolicyOverride.objects.filter(school=self.s1, policy_key="zap").exists()
        )

    def test_prune_does_not_touch_unmentioned_schools(self):
        TenantPolicyOverride.objects.create(school=self.s2, policy_key="other", value=1)
        apply_overrides_dict(
            self._payload({"school": "m3do1", "policy_key": "x", "value": 1}),
            prune=True,
        )
        # s2's override survives because the payload didn't mention school m3do2.
        self.assertTrue(
            TenantPolicyOverride.objects.filter(school=self.s2, policy_key="other").exists()
        )
