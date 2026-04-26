"""Phase B batches 4-13: domain snapshot table + resolver merge."""

from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.helpers import apply_payload_dict_to_site_settings_shallow_base
from apps.platform_runtime.site_settings_read_access import (
    get_effective_site_settings,
    get_platform_site_settings_record,
    invalidate_effective_site_settings_cache,
)
from apps.platform_runtime.models import PlatformPhaseBDomainSnapshot, RuntimeDefaults
from apps.platform_runtime.phase_b_domain_snapshots import (
    PHASE_B_SNAPSHOT_DOMAINS,
    diff_top_level_payload_keys,
    merge_phase_b_domain_snapshots_into_base,
    sync_phase_b_domain_snapshots_from_site,
)
from apps.platform_runtime.phase_b_operator_labels import (
    assert_operator_labels_align_with_snapshot_domains,
    phase_b_operator_card_text,
)


class PhaseBDomainSnapshotTests(TestCase):
    def test_save_creates_ten_domain_rows(self):
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        # Snapshots sync from SiteSettings.save(); get_or_create already persisted the row.
        self.assertEqual(
            PlatformPhaseBDomainSnapshot.objects.count(), len(PHASE_B_SNAPSHOT_DOMAINS)
        )
        for d in PHASE_B_SNAPSHOT_DOMAINS:
            self.assertTrue(PlatformPhaseBDomainSnapshot.objects.filter(pk=d).exists())
        row = PlatformPhaseBDomainSnapshot.objects.get(pk="policies_rules")
        self.assertEqual(len(row.payload_checksum), 64)
        self.assertIsInstance(row.payload_key_checksums, dict)

    def test_marketplace_snapshot_excludes_integration_secrets(self):
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.apply_feature_control_state(
            field_updates={"sms_api_key": "secret-do-not-snapshot-sms"}
        )
        rd = RuntimeDefaults.get_singleton()
        self.assertIsNotNone(rd)
        rd.ai_provider_api_key = "secret-do-not-snapshot-ai"
        rd.whatsapp_api_token = "secret-do-not-snapshot-wa"
        rd.marksheet_ocr_api_key = "secret-do-not-snapshot-ocr"
        rd.smtp_password = "secret-do-not-snapshot-smtp"
        rd.webhook_signing_secret = "secret-do-not-snapshot-webhook"
        rd.marketplace_partner_client_secret = "secret-do-not-snapshot-partner"
        rd.save(
            update_fields=[
                "ai_provider_api_key",
                "whatsapp_api_token",
                "marksheet_ocr_api_key",
                "smtp_password",
                "webhook_signing_secret",
                "marketplace_partner_client_secret",
                "updated_at",
            ]
        )
        sync_phase_b_domain_snapshots_from_site(site)
        row = PlatformPhaseBDomainSnapshot.objects.get(pk="marketplace_integrations")
        self.assertNotIn("sms_api_key", row.payload)
        self.assertNotIn("ai_provider_api_key", row.payload)
        self.assertNotIn("whatsapp_api_token", row.payload)
        self.assertNotIn("marksheet_ocr_api_key", row.payload)
        self.assertNotIn("smtp_password", row.payload)
        self.assertNotIn("webhook_signing_secret", row.payload)
        self.assertNotIn("marketplace_partner_client_secret", row.payload)

    def test_merge_overlays_payload_before_effective_read(self):
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        sync_phase_b_domain_snapshots_from_site(site)
        row = PlatformPhaseBDomainSnapshot.objects.get(pk="policies_rules")
        pl = dict(row.payload)
        pl["requests_reminder_interval_hours"] = 99
        row.payload = pl
        row.refresh_payload_metadata()
        row.save(
            update_fields=[
                "payload",
                "payload_key_count",
                "payload_checksum",
                "payload_key_checksums",
            ]
        )
        # RuntimeDefaults.payload wins over snapshots when both set; clear RT key so this
        # test isolates snapshot overlay behavior.
        from apps.platform_runtime.models import RuntimeDefaults

        rd = RuntimeDefaults.get_singleton()
        if rd:
            rd.requests_reminder_interval_hours = None
        if rd and isinstance(rd.payload, dict):
            pl_rt = dict(rd.payload)
            pl_rt.pop("requests_reminder_interval_hours", None)
            rd.payload = pl_rt
            rd.save(
                update_fields=[
                    "requests_reminder_interval_hours",
                    "payload",
                    "updated_at",
                ]
            )
        invalidate_effective_site_settings_cache()
        eff = get_effective_site_settings(request=None, school=None)
        self.assertEqual(getattr(eff, "requests_reminder_interval_hours", None), 99)

    def test_apply_payload_helper_sets_concrete_field(self):
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        from copy import copy

        shallow = copy(site)
        apply_payload_dict_to_site_settings_shallow_base(
            shallow, {"requests_reminder_interval_hours": 42}
        )
        self.assertEqual(shallow.requests_reminder_interval_hours, 42)

    def test_diff_top_level_payload_keys_detects_mismatch(self):
        live = {"a": 1, "b": {"x": 1}}
        stored = {"a": 2, "c": 3}
        d = diff_top_level_payload_keys(live, stored)
        self.assertIn("a", d["value_mismatch"])
        self.assertIn("b", d["only_live"])
        self.assertIn("c", d["only_stored"])
        self.assertGreater(d["changed_key_count"], 0)

    def test_merge_phase_b_is_safe_when_table_empty(self):
        PlatformPhaseBDomainSnapshot.objects.all().delete()
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        from copy import copy

        base = copy(site)
        merge_phase_b_domain_snapshots_into_base(base)
        self.assertIsNotNone(base)

    def test_operator_labels_align_with_snapshot_domains(self):
        assert_operator_labels_align_with_snapshot_domains()

    def test_operator_card_text_nonempty_for_each_domain(self):
        for d in PHASE_B_SNAPSHOT_DOMAINS:
            title, summary = phase_b_operator_card_text(d)
            self.assertNotEqual(title.strip(), "")
            self.assertNotEqual(summary.strip(), "")
