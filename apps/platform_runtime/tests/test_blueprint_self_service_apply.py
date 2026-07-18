"""Plan/tenant-scoped blueprints self-apply; operator blueprints stay gated.

Regression seal for the "Change request #14 is pending_approval" report: applying
an offline-first, tenant-scoped blueprint (low-connectivity-school) demanded
operator approval only because a *conditional go-live payment* proof was
mis-declared as an apply-time ``external_dependencies`` entry (which feeds
``blocked_by_external`` and forces ``requires_approval=True`` +
``can_apply=False``). The go-live PSP/settlement gate now lives in
``external_required_items`` (a capability gate, surfaced as a warning + on the
payment-readiness path) and no longer blocks apply.

The companion assertion proves the governance gate did NOT widen: an
operator-network blueprint (multi-campus-network) still requires approval,
now via ``requires_platform_operator`` in the change-set predicate rather than
its (removed) external dependency.
"""
from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.blueprint_preview import preview_blueprint
from apps.platform_runtime.configuration_change_set import generate_blueprint_change_set
from apps.schools.models import School


class BlueprintSelfServiceApplyTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Self Service School",
            slug="self-service-school",
            subdomain="self-service-school",
            is_active=True,
            settings={},
        )
        self.actor = User.objects.create_user(
            username="self_service_actor",
            password="x" * 10,
            role=User.Role.ADMIN,
        )

    def test_low_connectivity_blueprint_auto_applies_without_operator(self):
        change_set = generate_blueprint_change_set(
            "low-connectivity-school",
            school=self.school,
            actor=self.actor,
        )

        # The whole point of the fix: a tenant-scoped offline-first blueprint
        # applies with no governance detour.
        self.assertFalse(
            change_set["requires_approval"],
            msg="Offline-first tenant blueprint must not require operator approval.",
        )
        self.assertTrue(
            change_set["can_apply"],
            msg=f"Blueprint should be applyable: {change_set.get('dependency_blockers')}",
        )
        self.assertEqual(change_set["external_blockers"], [])

    def test_go_live_payment_gate_is_preserved_as_capability_not_blocker(self):
        # The PSP/settlement go-live gate survives — it is surfaced as a
        # capability requirement (external_required) and a warning, just not as
        # an apply-time blocker. And the bare-string tuple bug is fixed: the
        # item must be a single token, not char-exploded.
        preview = preview_blueprint("low-connectivity-school", school=self.school)

        self.assertEqual(preview["external_required"], ["live_payment_collection"])
        self.assertTrue(
            any("External dependencies" in w for w in preview["warnings"]),
            msg=preview["warnings"],
        )

    def test_other_tenant_scoped_payment_blueprints_also_self_apply(self):
        for key in ("cameroon-gce-school", "international-school"):
            with self.subTest(blueprint=key):
                change_set = generate_blueprint_change_set(
                    key,
                    school=self.school,
                    actor=self.actor,
                )
                self.assertFalse(
                    change_set["requires_approval"],
                    msg=f"{key} should self-apply within tenant scope.",
                )

    def test_operator_network_blueprint_still_requires_approval(self):
        # Governance did NOT widen: multi-campus-network is requires_platform_operator,
        # so it stays gated even though its external dependency was removed.
        change_set = generate_blueprint_change_set(
            "multi-campus-network",
            school=self.school,
            actor=self.actor,
            platform_operator=True,
        )

        self.assertTrue(
            change_set["requires_approval"],
            msg="Operator-network blueprint must remain governance-gated.",
        )
