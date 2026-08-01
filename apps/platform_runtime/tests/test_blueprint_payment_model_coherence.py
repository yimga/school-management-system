"""Readiness must not gate a blueprint on a rail its own contract says it does without.

Two blueprints declare a live-collection go-live gate while their own contracts
declare the opposite operating model:

* ``low-connectivity-school`` — ``local_constraints`` carries
  ``manual_receipt_reconciliation``, plus a "Manual payment reconciliation"
  workflow pack, a "Payments fallback" module, a "Manual audit" policy bundle
  and the ``payments.reconcile`` permission.
* ``cameroon-gce-school`` — ``local_constraints`` carries
  ``manual_payment_fallback`` and the checklist says "Set manual payment
  fallback".

The gate is weighed at 15, so both sat at 85 for every tenant — the offline-first
archetype being told it could not finish until it onboarded an online PSP, the
very thing a low-connectivity school exists to operate without.

The fix is deliberately in the METER, not the contract. An earlier attempt
removed the gate from the two contracts and was correctly caught by the existing
preview seals (``test_go_live_payment_gate_is_preserved_as_capability_not_blocker``,
``test_external_psp_items_are_marked_external_required``), which exist to stop
exactly that move: deleting a payment gate to make a number go up. Live
collection is a real, external, optional capability and the preview must keep
surfacing it as a capability requirement (never an apply blocker) so a school
that does want a live rail is still guided to one. It simply must not PIN the
readiness score for a school operating the model its blueprint prescribes.

This reads a BLUEPRINT CONTRACT fact and never tenant state —
``apps.finance.fee_collection_posture`` documents that a manual posture is never
inferred from the absence of a rail, because that would turn "this school never
set up payments" into "this school is done".
"""

from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.blueprint_contract import BASELINE_BLUEPRINTS, get_blueprint
from apps.platform_runtime.blueprint_preview import preview_blueprint
from apps.platform_runtime.readiness_meters import (
    _declares_manual_payment_model,
    blueprint_readiness,
)
from apps.schools.models import School

MANUAL_MODEL_BLUEPRINTS = ("low-connectivity-school", "cameroon-gce-school")
#: Declares a genuinely external settlement requirement — must stay weighed.
EXTERNAL_SETTLEMENT_BLUEPRINT = "international-school"


class BlueprintPaymentModelCoherenceTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Payment Model School",
            slug="payment-model-school",
            subdomain="payment-model-school",
            is_active=True,
        )

    def _readiness(self, key):
        preview = preview_blueprint(key, school=self.school, platform_operator=False)
        return blueprint_readiness(preview, school=self.school), preview

    def test_manual_model_blueprints_reach_100_without_a_live_rail(self):
        for key in MANUAL_MODEL_BLUEPRINTS:
            with self.subTest(blueprint=key):
                detail, _ = self._readiness(key)
                self.assertEqual(
                    detail["value"],
                    100,
                    f"{key} prescribes manual reconciliation yet reads "
                    f"{detail['value']} pending {detail['unmet']}",
                )

    def test_the_gate_is_still_declared_and_still_surfaced(self):
        """The fix must be in the meter — never by deleting the capability."""
        for key in MANUAL_MODEL_BLUEPRINTS:
            with self.subTest(blueprint=key):
                self.assertIn(
                    "live_payment_collection",
                    get_blueprint(key).external_required_items,
                    f"{key} lost its declared go-live capability",
                )
                _, preview = self._readiness(key)
                self.assertIn("live_payment_collection", preview["external_required"])
                # …and it is still a capability gate, never an apply blocker.
                self.assertTrue(preview["can_apply"])
                self.assertEqual(preview["external_hard_blockers"], [])

    def test_a_genuinely_external_blueprint_is_still_weighed(self):
        """Must-fire: the drop must not have become an unconditional pass."""
        self.assertFalse(
            _declares_manual_payment_model(
                {"blueprint_key": EXTERNAL_SETTLEMENT_BLUEPRINT}
            )
        )
        detail, _ = self._readiness(EXTERNAL_SETTLEMENT_BLUEPRINT)
        self.assertEqual(detail["value"], 85)
        self.assertEqual(detail["unmet"], ["Live payment onboarding"])

    def test_tenant_posture_is_never_inferred(self):
        """A blueprint silent on its payment model still resolves against the tenant."""
        for bp in BASELINE_BLUEPRINTS:
            constraints = {str(c).lower() for c in (bp.local_constraints or ())}
            declares_manual = _declares_manual_payment_model({"blueprint_key": bp.key})
            self.assertEqual(
                declares_manual,
                bool(
                    constraints
                    & {"manual_payment_fallback", "manual_receipt_reconciliation"}
                ),
                f"{bp.key}: drop must follow the contract, nothing else",
            )

    def test_helper_is_inert_for_packs_and_unknown_keys(self):
        """Packs share _external_checks and carry no blueprint_key."""
        self.assertFalse(_declares_manual_payment_model({}))
        self.assertFalse(_declares_manual_payment_model({"blueprint_key": ""}))
        self.assertFalse(_declares_manual_payment_model({"blueprint_key": "nope"}))

    def test_every_tenant_visible_blueprint_reaches_100_on_a_recorded_posture(self):
        """The one honest holdout must be closable by a tenant in one action."""
        from apps.finance.fee_collection_posture import (
            POSTURE_MANUAL,
            record_collection_posture,
        )

        record_collection_posture(self.school, mode=POSTURE_MANUAL, actor=None)
        self.school.refresh_from_db()
        from apps.platform_runtime.blueprint_contract import list_blueprints

        low = {}
        for row in list_blueprints(tenant_safe_only=True):
            detail, _ = self._readiness(row["key"])
            if detail["value"] < 100:
                low[row["key"]] = detail
        self.assertEqual(low, {}, f"below 100 after recording a posture: {low}")
