"""A blueprint-driven module change must land in BOTH module stores.

The platform resolves "is this module on for this school?" through
``is_feature_enabled``, which consults two stores in order:

1. ``School.features`` — a positive-only JSON grant (``{"library": true}``).
   A ``false`` value is not a veto, it simply fails to grant.
2. the toggle store — ``FeatureToggleDefinition`` / ``FeatureToggleState``,
   reached via ``resolve_module_enabled`` → ``resolve_toggle('module.<code>')``.
   This is the only place an "off" decision can actually be recorded, and it is
   the audited path (``set_toggle_state`` takes the acting user).

The tenant-facing Module Market writes **both** on every activate/deactivate.
The blueprint module bridge wrote only ``School.features``, so after a blueprint
enabled a module the two stores disagreed: features said ``True`` while the
toggle store still said ``False`` from the tenant's earlier deactivation. The
module resolved on only because the ``School.features`` short-circuit runs first
— a split-brain that any consumer reading the toggle store directly, or any
reordering of the resolution chain, turns back off. It also meant a
blueprint-driven module change was invisible to the audited toggle store.

These tests pin both directions: apply agrees, and rollback agrees.
"""

from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.blueprint_apply import apply_blueprint
from apps.platform_runtime.blueprint_contract import get_blueprint_or_raise
from apps.platform_runtime.blueprint_modules import enable_blueprint_modules
from apps.platform_runtime.blueprint_rollback import rollback_blueprint_installation
from apps.platform_runtime.models import BlueprintInstallation
from apps.schools.models import School, is_feature_enabled
from apps.siteconfig.feature_toggles import resolve_toggle, set_toggle_state

BLUEPRINT = "boarding-school"
# boarding-school's bridge resolves to exactly these two registry codes.
BRIDGE_CODES = ("dormitory", "parent_chat")


def _deactivate_like_the_module_market(school, code: str) -> None:
    """Reproduce apps/siteconfig/views.py::module_market's deactivate branch."""
    features = dict(school.features or {})
    features[code] = False
    school.features = features
    school.save(update_fields=["features"])
    set_toggle_state(
        f"module.{code}",
        enabled=False,
        school=school,
        label=f"Module: {code}",
        description=f"School-level module toggle for '{code}'.",
        category="modules",
        default_enabled=False,
    )
    school.refresh_from_db()


class BlueprintModuleStoreConsistencyTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Module Store School",
            slug="module-store-school",
            subdomain="module-store-school",
            is_active=True,
        )
        self.actor = User.objects.create_user(
            username="module_store_actor",
            password="x" * 8,
            role=User.Role.SUPERADMIN,
            is_staff=True,
        )

    def test_module_market_deactivation_actually_turns_a_module_off(self):
        """Baseline: the tenant's own control works, and modules start on."""
        self.assertTrue(is_feature_enabled(self.school, "dormitory"))

        _deactivate_like_the_module_market(self.school, "dormitory")

        self.assertFalse(is_feature_enabled(self.school, "dormitory"))

    def test_bridge_writes_the_toggle_store_not_only_school_features(self):
        _deactivate_like_the_module_market(self.school, "dormitory")

        enable_blueprint_modules(
            self.school, get_blueprint_or_raise(BLUEPRINT), persist=True
        )
        self.school.refresh_from_db()

        self.assertTrue(is_feature_enabled(self.school, "dormitory"))
        self.assertTrue(self.school.features.get("dormitory"))
        # The audited store must agree, not lag behind at False.
        self.assertIs(
            resolve_toggle("module.dormitory", school=self.school, fallback=None),
            True,
        )

    def test_apply_leaves_both_stores_agreeing_for_every_bridged_code(self):
        for code in BRIDGE_CODES:
            _deactivate_like_the_module_market(self.school, code)

        result = apply_blueprint(
            BLUEPRINT,
            school=self.school,
            actor=self.actor,
            confirmed=True,
            platform_operator=True,
            idempotency_key="module-store-apply",
        )
        self.school.refresh_from_db()

        self.assertTrue(result["ok"], msg=result)
        for code in BRIDGE_CODES:
            with self.subTest(code=code):
                self.assertTrue(is_feature_enabled(self.school, code))
                self.assertIs(
                    resolve_toggle(f"module.{code}", school=self.school, fallback=None),
                    True,
                )

    def test_rollback_leaves_both_stores_agreeing(self):
        applied = apply_blueprint(
            BLUEPRINT,
            school=self.school,
            actor=self.actor,
            confirmed=True,
            platform_operator=True,
            idempotency_key="module-store-rollback",
        )
        installation = BlueprintInstallation.objects.get(pk=applied["installation_id"])

        rollback_blueprint_installation(
            installation, actor=self.actor, confirmed=True
        )
        self.school.refresh_from_db()

        for code in BRIDGE_CODES:
            with self.subTest(code=code):
                # Rollback removed the grant, so the audited store must not still
                # be advertising an enable this blueprint no longer stands behind.
                self.assertFalse(self.school.features.get(code))
                self.assertIs(
                    resolve_toggle(f"module.{code}", school=self.school, fallback=None),
                    False,
                )
                self.assertFalse(is_feature_enabled(self.school, code))

    def test_rollback_does_not_touch_a_module_the_tenant_owns(self):
        """A module the tenant enabled itself is not the blueprint's to retract."""
        set_toggle_state(
            "module.library",
            enabled=True,
            school=self.school,
            label="Module: library",
            description="tenant choice",
            category="modules",
            default_enabled=False,
        )
        applied = apply_blueprint(
            BLUEPRINT,
            school=self.school,
            actor=self.actor,
            confirmed=True,
            platform_operator=True,
            idempotency_key="module-store-untouched",
        )
        installation = BlueprintInstallation.objects.get(pk=applied["installation_id"])

        rollback_blueprint_installation(installation, actor=self.actor, confirmed=True)
        self.school.refresh_from_db()

        self.assertIs(
            resolve_toggle("module.library", school=self.school, fallback=None), True
        )
        self.assertTrue(is_feature_enabled(self.school, "library"))
