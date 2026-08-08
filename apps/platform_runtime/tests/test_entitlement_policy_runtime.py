from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, tag

from apps.platform_runtime.entitlement_gates import (
    can_capability,
    can_role,
    gate_summary,
    invalidate_entitlement_cache,
)
from apps.schools.models import School
from apps.siteconfig.models import Plan


@tag("tenants_rls")
class EntitlementPolicyRuntimeTests(TestCase):
    def setUp(self):
        cache.clear()
        self.plan = Plan.objects.create(
            name="Gate Plan",
            slug="gate-plan",
            included_features=["reports"],
            is_active=True,
        )
        self.school = School.objects.create(
            name="Gate School",
            slug="gate-school",
            subdomain="gate-school",
            is_active=True,
            plan=self.plan,
        )

    def test_can_capability_respects_plan_features(self):
        self.assertTrue(can_capability(self.school, "reports", use_cache=False))
        self.assertFalse(can_capability(self.school, "migration_cloud", use_cache=False))

    def test_cache_invalidation_changes_subsequent_lookup(self):
        self.assertTrue(can_capability(self.school, "reports", use_cache=True))
        invalidate_entitlement_cache(self.school)
        summary = gate_summary(self.school)
        self.assertEqual(summary["school_id"], self.school.pk)
        self.assertIn("cache_prefix", summary)

    def test_null_school_denied(self):
        self.assertFalse(can_capability(None, "reports"))


class _EnumRole:
    """Stand-in for a ``User.Role`` TextChoices member (has ``.value``)."""

    value = "TEACHER"


class _FakeUser:
    def __init__(self, role, *, authenticated=True):
        self.role = role
        self.is_authenticated = authenticated


class CanRoleNormalizationTests(SimpleTestCase):
    """Seals a dead-guard fixed 2026-08-08.

    ``can_role`` used to do ``from apps.platform_runtime.role_registry import
    normalize_role`` inside a ``try/except (ImportError, ...)`` — but
    ``normalize_role`` was never defined, so the import raised ``ImportError``
    on EVERY call and was silently swallowed; the intended role-normalization
    primary path never ran (only the naive ``.strip().upper()`` fallback did).
    These are MUST-FIRE tests: if the ``normalize_role`` primitive is dropped
    from the role SOT again, the import + ``assertIs`` wiring check fail loudly
    instead of degrading to a masked fallback.
    """

    def test_normalize_role_lives_in_the_role_sot(self):
        # Direct seal for the exact regression: the symbol MUST exist in the SOT.
        from apps.platform_runtime.role_registry import normalize_role

        self.assertEqual(normalize_role("admin"), "ADMIN")
        self.assertEqual(normalize_role("  Proprietor "), "PROPRIETOR")
        self.assertEqual(normalize_role(_EnumRole()), "TEACHER")
        self.assertEqual(normalize_role(None), "")

    def test_can_role_is_wired_to_the_sot_primitive(self):
        # Structural seal: the gate must resolve the REAL SOT primitive, not a
        # locally-shadowed or masked fallback.
        from apps.platform_runtime import entitlement_gates, role_registry

        self.assertIs(entitlement_gates.normalize_role, role_registry.normalize_role)

    def test_can_role_matches_across_case_whitespace_and_enum(self):
        self.assertTrue(can_role(_FakeUser("admin"), "ADMIN"))
        self.assertTrue(can_role(_FakeUser("  ADMIN "), "admin"))
        self.assertTrue(can_role(_FakeUser(_EnumRole()), "teacher"))
        self.assertFalse(can_role(_FakeUser("parent"), "ADMIN"))

    def test_can_role_denies_anonymous_none_and_empty_request(self):
        self.assertFalse(can_role(None, "ADMIN"))
        self.assertFalse(can_role(_FakeUser("ADMIN", authenticated=False), "ADMIN"))
        # No valid requested roles → deny (not an accidental allow-all).
        self.assertFalse(can_role(_FakeUser("ADMIN"), ""))
