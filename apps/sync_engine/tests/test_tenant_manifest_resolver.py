"""
Chain-reaction proof: country profile -> tenant manifest -> offline.

These tests close the gap documented in
docs/generated/local_first_chain_reaction_truth_audit_2026_06_10.md — that the
tenant manifest compiler had zero production callers. They prove the resolver
reads a school's country and produces an offline manifest whose payment posture is
HONEST (placeholder corridors are never reported as collectable offline), and that
the live offline-bundle path now carries that manifest.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from apps.sync_engine.tenant_manifest_compiler import TenantManifestError
from apps.sync_engine.tenant_manifest_resolver import (
    build_school_offline_manifest,
    school_offline_manifest_dict,
)


def _school(**kwargs):
    base = {"id": 42, "schema_name": "tenant_42", "country_code": "CM", "default_language": ""}
    base.update(kwargs)
    return SimpleNamespace(**base)


class TenantManifestResolverTests(SimpleTestCase):
    def test_manifest_includes_ingestion_lexicon(self) -> None:
        m = build_school_offline_manifest(_school(country_code="CM"))
        lex = m.operational_context.get("ingestion_lexicon")
        self.assertIsInstance(lex, dict)
        self.assertEqual(lex.get("country_code"), "CM")
        self.assertTrue(lex.get("lexicon_mappings"))

    def test_defined_country_produces_country_enriched_manifest(self) -> None:
        m = build_school_offline_manifest(_school(country_code="CM"))
        self.assertEqual(m.data_policies["country"]["country_code"], "CM")
        self.assertTrue(m.data_policies["country"]["resolved"])
        # CM defaults to French in the localization seed.
        self.assertEqual(m.locale_default, "fr")
        self.assertTrue(m.checksum)
        # Offline capability flags flowed in from the offline-mode bundle SOT.
        self.assertTrue(m.feature_flags.get("enable_offline_form_queue"))

    def test_defined_corridor_payment_posture_is_honest_not_live(self) -> None:
        # No PSP adapter is `live` today, so even a DEFINED corridor must not claim
        # offline live collection.
        posture = build_school_offline_manifest(_school(country_code="CM")).data_policies["payment"]
        self.assertEqual(posture["data_state"], "defined")
        self.assertFalse(posture["live_collection"])

    def test_placeholder_corridor_never_reports_live_collection(self) -> None:
        # AD (Andorra) is a placeholder stub, not a researched corridor.
        posture = build_school_offline_manifest(_school(country_code="AD")).data_policies["payment"]
        self.assertEqual(posture["data_state"], "placeholder")
        self.assertFalse(posture["live_collection"])
        self.assertEqual(posture["readiness_tier"], "corridor_undefined")

    def test_unknown_country_degrades_safely(self) -> None:
        posture = build_school_offline_manifest(_school(country_code="")).data_policies["payment"]
        self.assertFalse(posture["live_collection"])
        self.assertEqual(posture["data_state"], "unknown")

    def test_manifest_is_deterministic(self) -> None:
        a = school_offline_manifest_dict(_school(country_code="KE"))
        b = school_offline_manifest_dict(_school(country_code="KE"))
        self.assertEqual(a["checksum"], b["checksum"])

    def test_manifest_scrubs_and_isolates_by_tenant(self) -> None:
        a = build_school_offline_manifest(_school(id=1, schema_name="tenant_1"))
        b = build_school_offline_manifest(_school(id=2, schema_name="tenant_2"))
        self.assertNotEqual(a.tenant_id_hash, b.tenant_id_hash)
        # raw tenant identifiers must not appear in the scrubbed manifest body
        self.assertNotIn("tenant_1", a.to_dict()["tenant_id_hash"])

    def test_school_without_identity_raises(self) -> None:
        with self.assertRaises(TenantManifestError):
            build_school_offline_manifest(SimpleNamespace(country_code="CM"))


class OfflineBundleCarriesManifestTests(SimpleTestCase):
    def test_dry_run_bundle_includes_country_manifest(self) -> None:
        # The live offline-bundle path threads the resolved manifest through to the
        # persisted backend flags. Exercise the dry-run path with the SiteSettings
        # record patched out so the test stays DB-free.
        from apps.platform_runtime.offline_mode_bundle import (
            apply_offline_mode_bundle_for_tenant,
        )

        manifest = school_offline_manifest_dict(_school(country_code="NG"))
        fake_site = SimpleNamespace(get_backend_feature_flags=lambda: {})
        with mock.patch(
            "apps.platform_runtime.helpers.get_platform_site_settings_record",
            return_value=fake_site,
        ):
            result = apply_offline_mode_bundle_for_tenant(dry_run=True, tenant_manifest=manifest)
        self.assertEqual(result["offline_tenant_manifest"], manifest)
        self.assertEqual(
            result["backend_flags"]["offline_tenant_manifest"]["data_policies"]["country"][
                "country_code"
            ],
            "NG",
        )
