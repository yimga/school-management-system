"""Helpcenter, migration pipeline, and marketplace wizard writer tests (batch 6)."""

from __future__ import annotations

from django.test import TestCase

from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle, SlaTier
from apps.registries.models import CountryRegistry
from apps.schools.models import School
from apps.setup_studio.wizard_resolvers import (
    write_helpcenter_fallbacks,
    write_helpcenter_tagging,
    write_helpcenter_validation,
    write_marketplace_catalog,
    write_marketplace_receipts,
    write_marketplace_storefront,
    write_migration_cleanup,
    write_migration_mapping,
    write_migration_seeding,
)


class HelpcenterWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="US", defaults={"name": "United States"})
        self.school = School.objects.create(
            name="Help School",
            slug="help-school",
            subdomain="help-school",
            country_code="US",
            is_active=True,
        )

    def test_tagging_fallbacks_and_validation(self):
        write_helpcenter_tagging(
            school=self.school,
            wizard_key="ai_helpcenter_knowledge_injection",
            step_key="context_tagging",
            payload={"value": ["all_parents", "teacher"]},
            actor_user_id=1,
        )
        write_helpcenter_fallbacks(
            school=self.school,
            wizard_key="ai_helpcenter_knowledge_injection",
            step_key="fallback_redirection_matrix",
            payload={"pairs": {"unknown_intent": "operator_ticket"}},
            actor_user_id=1,
        )
        write_helpcenter_validation(
            school=self.school,
            wizard_key="ai_helpcenter_knowledge_injection",
            step_key="core_validation_test",
            payload={"value": "How do I pay school fees online?"},
            actor_user_id=1,
        )
        self.school.refresh_from_db()
        cs = (self.school.settings or {}).get("customersuccess", {})
        self.assertEqual(cs.get("helpcenter_audience_tags"), ["all_parents", "teacher"])
        self.assertEqual(cs.get("helpcenter_fallbacks", {}).get("unknown_intent"), "operator_ticket")
        self.assertEqual(cs.get("helpcenter_validation", {}).get("probe_length"), 32)


class MigrationPipelineWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Migration School",
            slug="migration-school",
            subdomain="migration-school",
            country_code="CM",
            is_active=True,
        )
        self.bundle = MigrationBundle.objects.create(
            school=self.school,
            label="Wizard test bundle",
            intake_method=IntakeMethod.FILE_UPLOAD,
            sla_tier=SlaTier.SMALL,
            status=BundleStatus.PENDING,
            size_summary={"worker_log": []},
        )

    def test_mapping_cleanup_and_dry_run_seeding(self):
        write_migration_mapping(
            school=self.school,
            wizard_key="legacy_data_extraction_pipeline",
            step_key="field_vector_mapping",
            payload={"mapping": {"Student Name": "students.full_name"}},
            actor_user_id=1,
        )
        write_migration_cleanup(
            school=self.school,
            wizard_key="legacy_data_extraction_pipeline",
            step_key="inline_error_cleanup",
            payload={"confirm_known_errors": True},
            actor_user_id=1,
        )
        write_migration_seeding(
            school=self.school,
            wizard_key="legacy_data_extraction_pipeline",
            step_key="identity_core_seeding",
            payload={"value": "dry_run"},
            actor_user_id=1,
        )
        self.school.refresh_from_db()
        self.bundle.refresh_from_db()
        mc = (self.school.settings or {}).get("migration_cloud", {})
        self.assertIn("students.full_name", mc.get("field_vector_mapping", {}).values())
        self.assertEqual(mc.get("identity_seeding_mode"), "dry_run")
        summary = self.bundle.size_summary or {}
        self.assertIn("field_vector_mapping", summary)
        self.assertTrue(summary.get("inline_error_cleanup", {}).get("confirm_known_errors"))


class MarketplaceWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Market School",
            slug="market-school",
            subdomain="market-school",
            country_code="CM",
            is_active=True,
        )

    def test_storefront_catalog_and_receipts(self):
        write_marketplace_storefront(
            school=self.school,
            wizard_key="localized_activity_asset_marketplace",
            step_key="storefront_blueprinting",
            payload={
                "storefront_name": "Campus Shop",
                "default_currency": "XAF",
                "default_tax_inclusive": True,
            },
            actor_user_id=1,
        )
        write_marketplace_catalog(
            school=self.school,
            wizard_key="localized_activity_asset_marketplace",
            step_key="product_catalog_seed",
            payload={"value": {"file_name": "catalog.csv", "file_size": 1024}},
            actor_user_id=1,
        )
        write_marketplace_receipts(
            school=self.school,
            wizard_key="localized_activity_asset_marketplace",
            step_key="ticket_receipt_automation",
            payload={
                "receipt_template": "ticket_v1",
                "delivery_channel": "email",
                "include_qr_code": True,
            },
            actor_user_id=1,
        )
        self.school.refresh_from_db()
        mp = (self.school.settings or {}).get("marketplace", {})
        self.assertEqual(mp.get("storefront", {}).get("storefront_name"), "Campus Shop")
        self.assertEqual(len(mp.get("catalog_seeds", [])), 1)
        self.assertEqual(mp.get("receipt_automation", {}).get("delivery_channel"), "email")
        self.assertIn("marketplace_ppp", self.school.settings or {})
