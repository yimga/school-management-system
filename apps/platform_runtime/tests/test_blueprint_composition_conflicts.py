"""Composition-model enforcement for blueprint installs.

The contract has always declared a composition model — ``composition_role``
(base / regional_overlay / specialty_overlay / offline_overlay / operator_network)
and a curated ``compatible_blueprints`` adjacency list — and nothing enforced it.

Two consequences, both proven here:

* A tenant could apply two different *base* operating models to the same school.
  Each base carries its own ``billing_defaults.plan`` and ``offline_defaults.mode``,
  so the second apply silently clobbered the first. ``preview["conflicts"]`` stayed
  empty, ``can_apply`` stayed ``True``, and the "Conflict-free" readiness check
  (weight 25) scored full marks on a tenant whose operating model had just been
  overwritten.
* ``detect_dependency_conflicts`` was a **dead guard**: it reads
  ``conflicts_with_blueprints`` / ``conflicts_with_packs``, and across the whole
  catalog (8 blueprints, 174 packs) exactly zero contracts declare either. It
  returned ``[]`` unconditionally and always had. A negative test can never catch
  that, so the must-fire test below is the seal.
"""

from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.blueprint_apply import apply_blueprint
from apps.platform_runtime.blueprint_contract import get_blueprint_or_raise, list_blueprints
from apps.platform_runtime.blueprint_preview import preview_blueprint
from apps.platform_runtime.pack_dependency_graph import detect_dependency_conflicts
from apps.schools.models import School


def _conflict_codes(preview: dict) -> set[str]:
    return {str(row.get("code")) for row in preview.get("conflicts", [])}


class BlueprintCompositionConflictTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Composition School",
            slug="composition-school",
            subdomain="composition-school",
            is_active=True,
        )
        self.actor = User.objects.create_user(
            username="composition_actor",
            password="x" * 8,
            role=User.Role.SUPERADMIN,
            is_staff=True,
        )

    def _apply(self, key: str):
        result = apply_blueprint(
            key,
            school=self.school,
            actor=self.actor,
            confirmed=True,
            platform_operator=True,
            idempotency_key=f"composition-{key}",
        )
        self.assertTrue(result["ok"], msg=result)
        return result

    def test_second_base_operating_model_is_blocked(self):
        """Two bases contradict each other — the second must not apply silently."""
        self._apply("private-primary-school")

        preview = preview_blueprint("international-school", school=self.school)

        self.assertFalse(preview["can_apply"])
        self.assertIn("incompatible_base_blueprint", _conflict_codes(preview))
        message = " ".join(
            row.get("message", "") for row in preview["conflicts"]
        )
        # The message must name the blueprint standing in the way and the way out,
        # or the tenant is told "no" with nothing actionable.
        self.assertIn("private-primary-school", message)
        self.assertIn("roll", message.lower())

    def test_blocked_second_base_cannot_be_forced_through_apply(self):
        """The block must hold at the apply engine, not only in the preview."""
        self._apply("private-primary-school")

        result = apply_blueprint(
            "international-school",
            school=self.school,
            actor=self.actor,
            confirmed=True,
            platform_operator=True,
            idempotency_key="composition-forced",
        )

        self.assertFalse(result["ok"], msg=result)

    def test_compatible_overlay_still_applies_over_its_base(self):
        """The guard must not over-block: a declared-compatible overlay still applies."""
        self._apply("private-primary-school")

        preview = preview_blueprint("low-connectivity-school", school=self.school)

        self.assertTrue(preview["can_apply"], msg=preview["conflicts"])
        self.assertNotIn("incompatible_base_blueprint", _conflict_codes(preview))

    def test_reapplying_the_same_base_is_not_a_conflict(self):
        """Re-apply is idempotent, not a composition conflict."""
        self._apply("private-primary-school")

        preview = preview_blueprint("private-primary-school", school=self.school)

        self.assertTrue(preview["can_apply"], msg=preview["conflicts"])
        self.assertTrue(preview["already_applied"])

    def test_undeclared_overlay_pairing_warns_without_blocking(self):
        """Overlay adjacency may be incomplete, so it informs rather than blocks."""
        self._apply("private-primary-school")
        self._apply("boarding-school")

        preview = preview_blueprint("bilingual-school", school=self.school)

        self.assertTrue(preview["can_apply"], msg=preview["conflicts"])
        self.assertTrue(
            any("boarding-school" in w for w in preview["warnings"]),
            msg=preview["warnings"],
        )

    def test_rolled_back_blueprint_stops_blocking(self):
        """Rollback is the documented way out, so it must actually clear the block."""
        from apps.platform_runtime.blueprint_rollback import rollback_blueprint_installation
        from apps.platform_runtime.models import BlueprintInstallation

        applied = self._apply("private-primary-school")
        installation = BlueprintInstallation.objects.get(pk=applied["installation_id"])
        rollback_blueprint_installation(installation, actor=self.actor, confirmed=True)

        preview = preview_blueprint("international-school", school=self.school)

        self.assertTrue(preview["can_apply"], msg=preview["conflicts"])

    def test_rollback_supersedes_stale_sibling_applied_rows(self):
        """A version-bump duplicate must not keep blocking after rollback."""
        from apps.platform_runtime.blueprint_rollback import rollback_blueprint_installation
        from apps.platform_runtime.models import BlueprintInstallation

        first = self._apply("private-secondary-school")
        BlueprintInstallation.objects.create(
            school=self.school,
            blueprint_key="private-secondary-school",
            blueprint_version="9.9.9",
            installed_version="9.9.9",
            available_version="9.9.9",
            status=BlueprintInstallation.Status.APPLIED,
            applied_at=BlueprintInstallation.objects.get(pk=first["installation_id"]).applied_at,
            idempotency_key="stale-sibling-secondary",
            preview_snapshot={},
            applied_changes=[],
            rollback_snapshot={},
        )
        latest = (
            BlueprintInstallation.objects.filter(
                school=self.school, blueprint_key="private-secondary-school"
            )
            .order_by("-pk")
            .first()
        )
        rollback_blueprint_installation(latest, actor=self.actor, confirmed=True)

        preview = preview_blueprint("private-primary-school", school=self.school)
        self.assertTrue(preview["can_apply"], msg=preview["conflicts"])
        self.assertNotIn(
            "incompatible_base_blueprint",
            _conflict_codes(preview),
        )

    def test_orphan_settings_marker_does_not_block_after_rollback(self):
        """Stale settings markers must not outlive the installation row."""
        from apps.platform_runtime.blueprint_rollback import rollback_blueprint_installation
        from apps.platform_runtime.models import BlueprintInstallation

        applied = self._apply("private-secondary-school")
        installation = BlueprintInstallation.objects.get(pk=applied["installation_id"])
        rollback_blueprint_installation(installation, actor=self.actor, confirmed=True)
        self.school.settings.setdefault("blueprint_marketplace", {})[
            "private-secondary-school"
        ] = {"version": "1.0.0", "applied_at": "2020-01-01T00:00:00+00:00"}
        self.school.save(update_fields=["settings"])

        preview = preview_blueprint("private-primary-school", school=self.school)
        self.assertTrue(preview["can_apply"], msg=preview["conflicts"])
        self.school.refresh_from_db()
        self.assertNotIn(
            "private-secondary-school",
            (self.school.settings or {}).get("blueprint_marketplace", {}),
        )


class DependencyConflictMustFireTests(TestCase):
    """``detect_dependency_conflicts`` returned [] unconditionally. Prove it fires."""

    def setUp(self):
        self.school = School.objects.create(
            name="Must Fire School",
            slug="must-fire-school",
            subdomain="must-fire-school",
            is_active=True,
        )
        self.actor = User.objects.create_user(
            username="must_fire_actor",
            password="x" * 8,
            role=User.Role.SUPERADMIN,
            is_staff=True,
        )

    def test_detect_dependency_conflicts_fires_on_installed_base(self):
        apply_blueprint(
            "private-primary-school",
            school=self.school,
            actor=self.actor,
            confirmed=True,
            platform_operator=True,
            idempotency_key="must-fire-base",
        )

        conflicts = detect_dependency_conflicts(
            "international-school",
            target_type="blueprint",
            school=self.school,
        )

        self.assertTrue(conflicts, "conflict detection is dead — it can never fire")
        self.assertEqual(
            {row["code"] for row in conflicts},
            {"incompatible_base_blueprint"},
        )

    def test_detect_dependency_conflicts_is_silent_on_a_clean_tenant(self):
        self.assertEqual(
            detect_dependency_conflicts(
                "international-school",
                target_type="blueprint",
                school=self.school,
            ),
            [],
        )


class CompositionContractHygieneTests(TestCase):
    """Seals on the composition data itself, so enforcement stays meaningful."""

    def test_compatibility_adjacency_is_symmetric(self):
        """``a`` compatible with ``b`` must mean ``b`` compatible with ``a``.

        Enforcement reads this adjacency, so a one-sided entry would make a pairing
        legal in one install order and illegal in the other.
        """
        contracts = {row["key"]: get_blueprint_or_raise(row["key"]) for row in list_blueprints()}
        asymmetric: list[str] = []
        for key, contract in contracts.items():
            for other in contract.compatible_blueprints:
                peer = contracts.get(other)
                self.assertIsNotNone(peer, f"{key} names unknown blueprint {other}")
                if key not in peer.compatible_blueprints:
                    asymmetric.append(f"{key} -> {other} (not reciprocated)")
        self.assertEqual(asymmetric, [], "\n".join(asymmetric))

    def test_every_blueprint_declares_a_known_composition_role(self):
        known = {
            "base",
            "regional_overlay",
            "specialty_overlay",
            "offline_overlay",
            "operator_network",
        }
        for row in list_blueprints():
            contract = get_blueprint_or_raise(row["key"])
            self.assertIn(contract.composition_role, known, msg=contract.key)

    def test_at_least_one_base_exists_so_the_guard_is_reachable(self):
        roles = [get_blueprint_or_raise(r["key"]).composition_role for r in list_blueprints()]
        self.assertGreaterEqual(
            roles.count("base"),
            2,
            "base-conflict enforcement is unreachable with fewer than two bases",
        )
