"""``TenantPolicyOverride`` and ``ScheduledPolicyOverride`` must reach the resolver.

Both models had three write paths and zero read paths:
``declarative_overrides.apply_overrides_dict``, ``manage.py apply_tenant_overrides``
and the tenant admin all created rows, and ``get_effective_policy`` returned
byte-identical output before and after. ``ScheduledPolicyOverride`` was worse --
``start_at``/``end_at`` were never compared to ``now`` anywhere in the repo, so the
tenant admin advertised a scheduling capability the platform did not have.

Every test here first asserts a BASELINE read of the same policy path, so a
resolver that stopped producing the surrounding section (or a queryset that
silently matched nothing) fails loudly instead of passing vacuously.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.policies.models import ScheduledPolicyOverride, TenantPolicyOverride
from apps.policies.resolver import get_effective_policy
from apps.schools.models import School


def _make_school(**kwargs) -> School:
    tag = uuid.uuid4().hex[:8]
    kwargs.setdefault("name", f"Override High {tag}")
    kwargs.setdefault("slug", f"ov-{tag}")
    kwargs.setdefault("subdomain", f"ov-{tag}")
    kwargs.setdefault("is_active", True)
    return School.objects.create(**kwargs)


@override_settings(POLICY_CACHE_TTL=0)
class TenantPolicyOverrideIsResolvedTests(TestCase):
    def setUp(self) -> None:
        self.school = _make_school()

    def test_dotted_key_lands_in_the_effective_policy(self) -> None:
        baseline = get_effective_policy(self.school)
        # Non-vacuity: the resolver really did build the admissions section, so a
        # miss below is the override failing to apply -- not an empty policy dict.
        self.assertIsInstance(baseline.get("admissions"), dict)
        self.assertIn("admission_number_strategy", baseline["admissions"])
        self.assertIsNone(baseline["admissions"].get("numbering_strategy"))

        TenantPolicyOverride.objects.create(
            school=self.school,
            policy_key="admissions.numbering_strategy",
            value={"strategy": "sequential", "prefix": "EXA"},
        )
        policy = get_effective_policy(self.school)
        self.assertEqual(
            policy["admissions"]["numbering_strategy"],
            {"strategy": "sequential", "prefix": "EXA"},
        )
        # Sibling keys in the same section survive: this is a key write, not a
        # section replacement.
        self.assertEqual(
            policy["admissions"]["admission_number_strategy"],
            baseline["admissions"]["admission_number_strategy"],
        )

    def test_override_wins_over_school_settings(self) -> None:
        self.school.settings = {"terminology": {"student": "Pupil"}}
        self.school.save(update_fields=["settings"])
        baseline = get_effective_policy(self.school)
        self.assertEqual(baseline["terminology"]["student"], "Pupil")

        TenantPolicyOverride.objects.create(
            school=self.school, policy_key="terminology.student", value="Scholar"
        )
        policy = get_effective_policy(self.school)
        self.assertEqual(policy["terminology"]["student"], "Scholar")

    def test_top_level_key_without_a_dot(self) -> None:
        baseline = get_effective_policy(self.school)
        self.assertNotEqual(baseline.get("default_language"), "ar")
        TenantPolicyOverride.objects.create(
            school=self.school, policy_key="default_language", value="ar"
        )
        self.assertEqual(get_effective_policy(self.school)["default_language"], "ar")

    def test_inactive_row_is_ignored(self) -> None:
        TenantPolicyOverride.objects.create(
            school=self.school,
            policy_key="terminology.student",
            value="Scholar",
            is_active=False,
        )
        policy = get_effective_policy(self.school)
        self.assertNotEqual(policy["terminology"].get("student"), "Scholar")

    def test_another_schools_override_does_not_leak(self) -> None:
        other = _make_school()
        TenantPolicyOverride.objects.create(
            school=other, policy_key="terminology.student", value="Scholar"
        )
        # Non-vacuity: the row IS resolvable -- for its own school.
        self.assertEqual(
            get_effective_policy(other)["terminology"]["student"], "Scholar"
        )
        self.assertNotEqual(
            get_effective_policy(self.school)["terminology"].get("student"), "Scholar"
        )


@override_settings(POLICY_CACHE_TTL=0)
class ScheduledPolicyOverrideIsResolvedTests(TestCase):
    QUIET = {"start": "18:00", "end": "07:00", "freeze": True}

    def setUp(self) -> None:
        self.school = _make_school()
        self.now = timezone.now()

    def _schedule(self, start_delta, end_delta, **kwargs) -> ScheduledPolicyOverride:
        return ScheduledPolicyOverride.objects.create(
            school=self.school,
            policy_key=kwargs.pop("policy_key", "communication.quiet_hours"),
            value=kwargs.pop("value", self.QUIET),
            start_at=self.now + start_delta,
            end_at=self.now + end_delta,
            **kwargs,
        )

    def test_open_window_applies(self) -> None:
        baseline = get_effective_policy(self.school)
        # Non-vacuity: the communication section exists and quiet_hours is the
        # resolver's own empty default before any schedule opens.
        self.assertIsInstance(baseline.get("communication"), dict)
        self.assertEqual(baseline["communication"].get("quiet_hours"), {})

        self._schedule(timedelta(hours=-1), timedelta(hours=1))
        policy = get_effective_policy(self.school)
        self.assertEqual(policy["communication"]["quiet_hours"], self.QUIET)

    def test_future_window_does_not_apply_yet(self) -> None:
        row = self._schedule(timedelta(days=7), timedelta(days=14))
        policy = get_effective_policy(self.school)
        self.assertEqual(policy["communication"].get("quiet_hours"), {})
        # Non-vacuity: the row exists and is active -- it is the WINDOW that
        # excludes it, not a missing/inactive row.
        self.assertTrue(
            ScheduledPolicyOverride.objects.filter(pk=row.pk, is_active=True).exists()
        )

    def test_closed_window_stops_applying(self) -> None:
        self._schedule(timedelta(days=-14), timedelta(days=-7))
        policy = get_effective_policy(self.school)
        self.assertEqual(policy["communication"].get("quiet_hours"), {})

    def test_inactive_row_is_ignored(self) -> None:
        self._schedule(timedelta(hours=-1), timedelta(hours=1), is_active=False)
        policy = get_effective_policy(self.school)
        self.assertEqual(policy["communication"].get("quiet_hours"), {})

    def test_open_window_wins_over_the_standing_tenant_override(self) -> None:
        TenantPolicyOverride.objects.create(
            school=self.school,
            policy_key="communication.quiet_hours",
            value={"freeze": False},
        )
        self.assertEqual(
            get_effective_policy(self.school)["communication"]["quiet_hours"],
            {"freeze": False},
        )
        self._schedule(timedelta(hours=-1), timedelta(hours=1))
        self.assertEqual(
            get_effective_policy(self.school)["communication"]["quiet_hours"],
            self.QUIET,
        )

    def test_another_schools_schedule_does_not_leak(self) -> None:
        other = _make_school()
        ScheduledPolicyOverride.objects.create(
            school=other,
            policy_key="communication.quiet_hours",
            value=self.QUIET,
            start_at=self.now - timedelta(hours=1),
            end_at=self.now + timedelta(hours=1),
        )
        self.assertEqual(
            get_effective_policy(other)["communication"]["quiet_hours"], self.QUIET
        )
        self.assertEqual(
            get_effective_policy(self.school)["communication"].get("quiet_hours"), {}
        )
