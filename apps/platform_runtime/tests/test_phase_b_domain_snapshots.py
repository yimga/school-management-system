"""Phase B batches 4-13: domain snapshot table + resolver merge."""

from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.helpers import (
    apply_payload_dict_to_site_settings_shallow_base,
    get_effective_site_settings,
    get_platform_site_settings_record,
    invalidate_effective_site_settings_cache,
)
from apps.platform_runtime.models import PlatformPhaseBDomainSnapshot
from apps.platform_runtime.phase_b_domain_snapshots import (
    PHASE_B_SNAPSHOT_DOMAINS,
    merge_phase_b_domain_snapshots_into_base,
    sync_phase_b_domain_snapshots_from_site,
)
class PhaseBDomainSnapshotTests(TestCase):
    def test_save_creates_ten_domain_rows(self):
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.save()
        self.assertEqual(
            PlatformPhaseBDomainSnapshot.objects.count(), len(PHASE_B_SNAPSHOT_DOMAINS)
        )
        for d in PHASE_B_SNAPSHOT_DOMAINS:
            self.assertTrue(PlatformPhaseBDomainSnapshot.objects.filter(pk=d).exists())

    def test_marketplace_snapshot_excludes_sms_api_key(self):
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        site.sms_api_key = "secret-do-not-snapshot"
        site.save()
        row = PlatformPhaseBDomainSnapshot.objects.get(pk="marketplace_integrations")
        self.assertNotIn("sms_api_key", row.payload)

    def test_merge_overlays_payload_before_effective_read(self):
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        sync_phase_b_domain_snapshots_from_site(site)
        row = PlatformPhaseBDomainSnapshot.objects.get(pk="policies_rules")
        pl = dict(row.payload)
        pl["requests_reminder_interval_hours"] = 99
        row.payload = pl
        row.save(update_fields=["payload"])
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

    def test_merge_phase_b_is_safe_when_table_empty(self):
        PlatformPhaseBDomainSnapshot.objects.all().delete()
        site = get_platform_site_settings_record(create=True)
        self.assertIsNotNone(site)
        from copy import copy

        base = copy(site)
        merge_phase_b_domain_snapshots_into_base(base)
        self.assertIsNotNone(base)
