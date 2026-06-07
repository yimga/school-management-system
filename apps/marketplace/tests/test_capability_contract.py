"""Wave 1 — capability contract on first-party catalog seed."""

from django.test import SimpleTestCase

from apps.marketplace.capability_contract import (
    TOP_15_APP_SLUGS,
    enrich_manifest_capability_bindings,
    infer_capability_bindings,
    manifest_has_capability_contract,
    validate_capability_bindings,
)
from apps.marketplace.management.commands.seed_marketplace_apps import FIRST_PARTY_APPS


class CapabilityContractSeedTests(SimpleTestCase):
    def test_every_first_party_app_has_valid_contract_after_enrich(self):
        for app_def in FIRST_PARTY_APPS:
            slug = app_def["slug"]
            manifest = enrich_manifest_capability_bindings(slug, app_def.get("manifest") or {})
            ok, errors = validate_capability_bindings(manifest)
            self.assertTrue(ok, msg=f"{slug}: {errors}")
            self.assertTrue(manifest_has_capability_contract(manifest), msg=slug)

    def test_top_15_slugs_have_package_binding(self):
        for slug in TOP_15_APP_SLUGS:
            bindings = infer_capability_bindings(slug, {})
            kinds = {b["kind"] for b in bindings}
            self.assertIn(
                "package_id",
                kinds,
                msg=f"{slug} should declare package_id binding",
            )

    def test_transport_app_enables_transport_feature(self):
        bindings = infer_capability_bindings("transport-bus-tracker", {})
        feats = [b["target"] for b in bindings if b["kind"] == "feature"]
        self.assertIn("transport", feats)
