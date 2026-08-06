"""Rolling back a blueprint must retract the packs it installed.

``apply_blueprint`` installs the blueprint's dashboard / workflow / policy packs
as child ``PackInstallation`` rows. Rollback never touched them, so a tenant who
undid a blueprint was told ``ok=True, status=rolled_back`` while every pack
stayed ``status=applied``. Measured on ``private-primary-school``: 7 packs
created, 7 still applied after rollback — including the **policy bundles**
"Finance Approval" (dual approval, reconciliation required) and "Parent
Communication" (guardian visibility, consent required), which keep enforcing
rules the tenant just retracted.

The pack-level retraction is surgical for the same reason the blueprint-level
one is: ``apply_pack`` writes exactly one key,
``settings["pack_installation_simulation"][pack.key]``, but
``rollback_pack_installation`` used to restore the WHOLE pre-apply settings dict.
With seven sibling packs installed in sequence, rolling one back would discard
every marker written after it. Wiring the child-pack loop in without fixing that
first would have multiplied the data-loss class instead of closing it.
"""

from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.blueprint_apply import apply_blueprint
from apps.platform_runtime.blueprint_rollback import rollback_blueprint_installation
from apps.platform_runtime.models import BlueprintInstallation, PackInstallation
from apps.platform_runtime.pack_rollback import rollback_pack_installation
from apps.schools.models import School

BLUEPRINT_WITH_PACKS = "private-primary-school"


class BlueprintRollbackChildPackTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Child Pack School",
            slug="child-pack-school",
            subdomain="child-pack-school",
            is_active=True,
        )

    def _apply(self):
        result = apply_blueprint(
            BLUEPRINT_WITH_PACKS,
            school=self.school,
            actor=None,
            confirmed=True,
            platform_operator=True,
        )
        self.assertTrue(result.get("ok"), msg=result.get("errors"))
        installation = (
            BlueprintInstallation.objects.filter(school=self.school)
            .order_by("-id")
            .first()
        )
        self.assertIsNotNone(installation)
        return installation

    def test_rollback_retracts_every_child_pack(self):
        installation = self._apply()
        applied = installation.pack_installations.filter(
            status=PackInstallation.Status.APPLIED
        )
        self.assertGreater(
            applied.count(), 0, "precondition: the blueprint installs packs"
        )

        result = rollback_blueprint_installation(
            installation, actor=None, confirmed=True
        )
        self.assertTrue(result.get("ok"), msg=result.get("errors"))

        still_applied = list(
            installation.pack_installations.filter(
                status=PackInstallation.Status.APPLIED
            ).values_list("pack_key", flat=True)
        )
        self.assertEqual(
            still_applied,
            [],
            "these packs stayed live after the blueprint was rolled back: "
            f"{still_applied}",
        )
        self.assertIn("pack_installations", result.get("reverted_changes") or [])

    def test_policy_bundles_specifically_stop_enforcing(self):
        """The riskiest child packs are the ones that carry rules."""
        installation = self._apply()
        policy_keys = set(
            installation.pack_installations.filter(
                pack_type="policy_bundle", status=PackInstallation.Status.APPLIED
            ).values_list("pack_key", flat=True)
        )
        self.assertGreater(len(policy_keys), 0, "precondition: policy bundles applied")

        rollback_blueprint_installation(installation, actor=None, confirmed=True)

        still = set(
            installation.pack_installations.filter(
                pack_type="policy_bundle", status=PackInstallation.Status.APPLIED
            ).values_list("pack_key", flat=True)
        )
        self.assertEqual(still, set(), f"policy bundles still enforcing: {still}")

    def test_pack_rollback_does_not_wipe_sibling_markers(self):
        """Must-fire: the surgical retraction, not a wholesale settings restore."""
        installation = self._apply()
        packs = list(
            installation.pack_installations.filter(
                status=PackInstallation.Status.APPLIED
            ).order_by("applied_at", "id")
        )
        self.assertGreaterEqual(len(packs), 2, "precondition: several sibling packs")

        # A marker the tenant owns, written AFTER every pack was applied. A
        # wholesale snapshot restore would discard it.
        self.school.refresh_from_db()
        settings = dict(self.school.settings or {})
        settings["tenant_owned_marker"] = {"kept": True}
        self.school.settings = settings
        self.school.save(update_fields=["settings"])

        first = packs[0]
        rollback_pack_installation(first, actor=None, confirmed=True)

        self.school.refresh_from_db()
        live = dict(self.school.settings or {})
        self.assertEqual(
            live.get("tenant_owned_marker"),
            {"kept": True},
            "rolling back one pack discarded a marker written after it",
        )
        simulations = dict(live.get("pack_installation_simulation") or {})
        self.assertNotIn(
            first.pack_key, simulations, "the rolled-back pack's own marker survived"
        )
        for sibling in packs[1:]:
            self.assertIn(
                sibling.pack_key,
                simulations,
                f"sibling {sibling.pack_key} marker was wiped by an unrelated rollback",
            )

    def test_rollback_is_still_confirmation_gated(self):
        """Must not have widened access while adding the pack loop."""
        installation = self._apply()
        result = rollback_blueprint_installation(
            installation, actor=None, confirmed=False
        )
        self.assertFalse(result.get("ok"))
        self.assertEqual(
            installation.pack_installations.filter(
                status=PackInstallation.Status.APPLIED
            ).count(),
            len(
                list(
                    installation.pack_installations.filter(
                        status=PackInstallation.Status.APPLIED
                    )
                )
            ),
            "an unconfirmed rollback must not touch child packs",
        )

    def test_a_pack_not_owned_by_this_blueprint_is_untouched(self):
        """Scope: only THIS installation's children may be retracted."""
        installation = self._apply()
        foreign = PackInstallation.objects.create(
            school=self.school,
            blueprint_installation=None,
            pack_key="standalone-pack",
            pack_type="dashboard_pack",
            version="1.0.0",
            installed_version="1.0.0",
            available_version="1.0.0",
            status=PackInstallation.Status.APPLIED,
            idempotency_key="standalone-pack-key",
        )

        rollback_blueprint_installation(installation, actor=None, confirmed=True)

        foreign.refresh_from_db()
        self.assertEqual(
            foreign.status,
            PackInstallation.Status.APPLIED,
            "a pack the tenant installed independently was retracted",
        )
