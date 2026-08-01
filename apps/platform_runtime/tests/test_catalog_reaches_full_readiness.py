"""Every tenant-safe blueprint and pack can actually reach 100.

A readiness meter is only honest if 100 is reachable. Three separate defects had
made it unreachable — a hardcoded client-proof literal, an offline verdict that a
payment gate could overwrite, and a live-payment check that read a static
contract tuple no tenant could satisfy — and each was invisible because nothing
asserted the ceiling.

This is that assertion. It is deliberately catalog-wide rather than
example-based: a new blueprint or pack that ships with an unsatisfiable
requirement turns it red on the day it lands, not months later when someone
wonders why the bar reads 85.
"""
from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from apps.finance.fee_collection_posture import POSTURE_MANUAL, record_collection_posture
from apps.platform_runtime.blueprint_contract import (
    BASELINE_BLUEPRINTS,
    list_blueprints,
)
from apps.platform_runtime.blueprint_preview import preview_blueprint
from apps.platform_runtime.pack_contract import _all_packs, list_packs
from apps.platform_runtime.pack_preview import preview_pack
from apps.platform_runtime.readiness_meters import blueprint_readiness, pack_readiness
from apps.schools.models import School

_NO_RAILS = {"stripe_connect": False, "verified_corridors": []}

# Wording that makes an external requirement CONDITIONAL — i.e. a go-live
# capability gate, not something that must be true before the config can apply.
_CONDITIONAL_MARKERS = (" if ", " when ", "optional", "conditional")


class CatalogReachesFullReadinessTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Readiness Ceiling School",
            slug="readiness-ceiling-school",
            subdomain="readiness-ceiling-school",
            is_active=True,
            settings={},
        )

    def _settle_collection(self):
        record_collection_posture(self.school, mode=POSTURE_MANUAL, note="Cash at bursary")
        self.school.refresh_from_db()

    def test_every_tenant_safe_blueprint_reaches_100(self):
        self._settle_collection()
        short = {}
        with patch(
            "apps.finance.fee_collection_posture._live_rail_evidence",
            return_value=dict(_NO_RAILS),
        ):
            for row in list_blueprints(tenant_safe_only=True):
                preview = preview_blueprint(row["key"], school=self.school)
                result = blueprint_readiness(preview, school=self.school)
                if result["value"] != 100:
                    short[row["key"]] = (result["value"], result["unmet"])

        self.assertEqual(short, {}, msg=f"Blueprints that cannot reach 100: {short}")

    def test_every_tenant_safe_pack_reaches_100(self):
        self._settle_collection()
        short = {}
        with patch(
            "apps.finance.fee_collection_posture._live_rail_evidence",
            return_value=dict(_NO_RAILS),
        ):
            for row in list_packs(tenant_safe_only=True):
                preview = preview_pack(
                    row["key"], pack_type=row["pack_type"], school=self.school
                )
                result = pack_readiness(preview, school=self.school)
                if result["value"] != 100:
                    short[row["key"]] = (result["value"], result["unmet"])

        self.assertEqual(short, {}, msg=f"Packs that cannot reach 100: {short}")

    def test_the_ceiling_test_is_not_vacuous(self):
        # MUST-FIRE: without a settled collection posture the payment-gated
        # blueprints are honestly short of 100. If this ever passes trivially,
        # the two tests above are asserting nothing.
        with patch(
            "apps.finance.fee_collection_posture._live_rail_evidence",
            return_value=dict(_NO_RAILS),
        ):
            values = {
                row["key"]: blueprint_readiness(
                    preview_blueprint(row["key"], school=self.school), school=self.school
                )["value"]
                for row in list_blueprints(tenant_safe_only=True)
            }

        gated = {key: value for key, value in values.items() if value < 100}
        self.assertTrue(
            gated,
            msg="No blueprint declares a go-live gate any more — the ceiling tests are vacuous.",
        )
        for key, value in gated.items():
            self.assertEqual(value, 85, msg=f"{key} should be short only the payment gate.")

    def test_no_conditional_requirement_is_declared_as_a_hard_blocker(self):
        # The defect class this whole wave chased, in one assertion. A phrase
        # like "PSP proof IF live collection is enabled" describes something
        # that may never apply to a given school; declaring it in
        # external_dependencies makes it an apply-time blocker and forces a
        # governance detour on a tenant that will never need it. Conditional
        # requirements belong in external_required_items.
        offenders = []
        for contract in list(BASELINE_BLUEPRINTS) + list(_all_packs()):
            for item in contract.external_dependencies:
                lowered = f" {item.lower()} "
                if any(marker in lowered for marker in _CONDITIONAL_MARKERS):
                    offenders.append((contract.key, item))

        self.assertEqual(
            offenders,
            [],
            msg=(
                "Conditional go-live requirements declared as apply-time blockers: "
                f"{offenders}. Move them to external_required_items."
            ),
        )
