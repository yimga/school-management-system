"""Module availability must not depend on whether a listing page was rendered.

``FeatureToggleDefinition`` rows for ``module.<code>`` are seeded **lazily**, by
``apps.schools.feature_registry.get_available_modules`` — which runs when the
module market is listed. ``resolve_toggle`` returns its ``fallback`` when no
definition row exists, and the fallback handed in was the policy value (False).

So on any database where that page had never been opened — a freshly provisioned
tenant, a self-host / edge install, a restored backup, a fresh test database —
every declared module resolved to **False**, and all ten ``@require_feature``
surfaces (library, transport, canteen, inventory, clinic, timetabling,
substitutes, visitor log, facilities, POS) answered
``403 This module is not enabled for your school``. Then someone opened the
module market once and all sixteen silently switched on, platform-wide.

That is the opposite of what the registry declares. ``ensure_module_registry_seeded``
stamps ``default_enabled=True`` with an explicit T21 comment: modules ship
default-ON unless an operator turns one off. The declared default now applies
whether or not the lazy seed has run, so the two databases agree.
"""

from __future__ import annotations

from django.test import TestCase

from apps.policies_rules.models import FeatureToggleDefinition
from apps.schools.feature_registry import (
    MODULE_DEFAULT_ENABLED,
    registry_module_codes,
)
from apps.schools.models import School, is_feature_enabled
from apps.siteconfig.feature_toggles import set_toggle_state


class ModuleDefaultAvailabilityTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Default Availability School",
            slug="default-availability-school",
            subdomain="default-availability-school",
            is_active=True,
        )
        # Reproduce a database whose module market has never been rendered.
        FeatureToggleDefinition.objects.filter(key__startswith="module.").delete()

    def test_every_declared_module_is_available_before_any_seeding(self):
        self.assertEqual(
            FeatureToggleDefinition.objects.filter(key__startswith="module.").count(),
            0,
            "precondition: no module definitions seeded",
        )

        unavailable = [
            code
            for code in sorted(registry_module_codes())
            if not is_feature_enabled(self.school, code)
        ]

        self.assertEqual(
            unavailable,
            [],
            "these modules 403 on a tenant whose module market was never opened: "
            + ", ".join(unavailable),
        )

    def test_listing_the_catalog_does_not_change_the_answer(self):
        """The lazy seed must be an implementation detail, not a behaviour switch."""
        before = {
            code: is_feature_enabled(self.school, code)
            for code in sorted(registry_module_codes())
        }

        from apps.schools.feature_registry import get_available_modules

        get_available_modules()
        self.school.refresh_from_db()

        after = {
            code: is_feature_enabled(self.school, code)
            for code in sorted(registry_module_codes())
        }

        self.assertEqual(before, after)

    def test_an_explicit_per_school_opt_out_still_wins(self):
        """Must-fire: the default must not have become an unconditional yes."""
        set_toggle_state(
            "module.library",
            enabled=False,
            school=self.school,
            label="Module: library",
            description="tenant opted out",
            category="modules",
        )
        self.school.refresh_from_db()

        self.assertFalse(is_feature_enabled(self.school, "library"))
        # and it is genuinely scoped to this school only
        other = School.objects.create(
            name="Other Availability School",
            slug="other-availability-school",
            subdomain="other-availability-school",
            is_active=True,
        )
        self.assertTrue(is_feature_enabled(other, "library"))

    def test_a_non_module_code_is_not_granted_by_the_module_default(self):
        """The default applies to declared modules only, never to arbitrary codes."""
        self.assertNotIn("definitely_not_a_module", registry_module_codes())
        self.assertFalse(is_feature_enabled(self.school, "definitely_not_a_module"))

    def test_registry_default_constant_is_the_single_source(self):
        """Seeded rows must carry the same default the resolver applies unseeded."""
        from apps.schools.feature_registry import get_available_modules

        get_available_modules()

        defaults = set(
            FeatureToggleDefinition.objects.filter(
                key__startswith="module."
            ).values_list("default_enabled", flat=True)
        )

        self.assertEqual(defaults, {MODULE_DEFAULT_ENABLED})
