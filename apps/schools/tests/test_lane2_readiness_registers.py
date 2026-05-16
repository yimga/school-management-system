"""Lane-2 readiness registers: SOT integrity tests.

PSP adapters, SOC2 controls, and pilot tracker each have invariants:

  - Slugs / IDs are unique.
  - Statuses are from a known whitelist.
  - When a row claims to be `live` / `implemented`, the proof artifact must
    actually exist (route resolves OR model loads).
  - Cross-register references (pilot.blocking_psps, pilot.blocking_features)
    point at real registered entries.

Drift here = we are claiming external preparedness we don't actually have.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.test import TestCase
from django.urls import NoReverseMatch, reverse

from apps.billing.psp_adapter_registry import PSP_REGISTER, psp_slugs
from apps.compliance.soc2_control_register import SOC2_REGISTER, control_ids
from apps.sales.pilot_register import PILOT_REGISTER


URLCONFS = ("config.urls", "config.tenant_urls", "config.manager_urls")


def _route_resolves(name: str) -> bool:
    for uc in URLCONFS:
        try:
            reverse(name, urlconf=uc)
            return True
        except NoReverseMatch:
            continue
    return False


class PSPRegisterTests(TestCase):
    def test_slugs_unique(self):
        slugs = [p.psp_slug for p in PSP_REGISTER]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_status_whitelist(self):
        for p in PSP_REGISTER:
            self.assertIn(p.adapter_status, {"live", "in_progress", "planned"}, p.psp_slug)

    def test_live_psps_have_proof(self):
        for p in PSP_REGISTER:
            if p.adapter_status != "live":
                continue
            has_proof = False
            if p.proof_route_name and _route_resolves(p.proof_route_name):
                has_proof = True
            if p.proof_model:
                try:
                    app_label, model_name = p.proof_model.split(".", 1)
                    django_apps.get_model(app_label, model_name)
                    has_proof = True
                except (LookupError, ValueError):
                    pass
            self.assertTrue(has_proof, f"{p.psp_slug} is live but has no resolvable proof")


class SOC2RegisterTests(TestCase):
    def test_control_ids_unique(self):
        ids = [c.control_id for c in SOC2_REGISTER]
        self.assertEqual(len(ids), len(set(ids)))

    def test_status_whitelist(self):
        for c in SOC2_REGISTER:
            self.assertIn(c.status, {"implemented", "partial", "planned"}, c.control_id)

    def test_implemented_controls_have_evidence_source(self):
        for c in SOC2_REGISTER:
            if c.status != "implemented":
                continue
            has_evidence = bool(
                c.evidence_route_name or c.evidence_model or c.evidence_scanner
            )
            self.assertTrue(has_evidence, f"{c.control_id} implemented with no evidence source")

    def test_implemented_route_evidence_resolves(self):
        for c in SOC2_REGISTER:
            if c.status != "implemented" or not c.evidence_route_name:
                continue
            self.assertTrue(
                _route_resolves(c.evidence_route_name),
                f"{c.control_id} evidence_route_name={c.evidence_route_name!r} doesn't resolve",
            )


class PilotRegisterTests(TestCase):
    def test_slugs_unique(self):
        slugs = [p.pilot_slug for p in PILOT_REGISTER]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_stage_whitelist(self):
        valid = {"prospect", "mou", "provisioning", "live", "paid", "paused", "lost"}
        for p in PILOT_REGISTER:
            self.assertIn(p.stage, valid, p.pilot_slug)

    def test_blocking_psps_reference_real_rows(self):
        known = psp_slugs()
        for p in PILOT_REGISTER:
            for slug in p.blocking_psps:
                self.assertIn(
                    slug, known,
                    f"{p.pilot_slug} blocking_psps references unknown PSP {slug!r}",
                )

    def test_blocking_features_reference_real_rows(self):
        from apps.schools.feature_gap_register import feature_slugs
        known = feature_slugs()
        for p in PILOT_REGISTER:
            for slug in p.blocking_features:
                self.assertIn(
                    slug, known,
                    f"{p.pilot_slug} blocking_features references unknown feature {slug!r}",
                )
