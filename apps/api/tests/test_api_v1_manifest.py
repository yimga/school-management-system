import json
from pathlib import Path

from django.conf import settings
from django.test import TestCase


class ApiV1ManifestTests(TestCase):
    def test_manifest_json(self):
        r = self.client.get("/api/v1/manifest.json")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data.get("version"), "1.0")
        self.assertIn("oneroster_v1p1", data.get("endpoints", {}))
        self.assertIn("developer_public_api_doc", data.get("endpoints", {}))
        ep = data.get("endpoints") or {}
        self.assertIn("/api/v1/me/schools", ep.get("me_schools", ""))
        self.assertIn("/api/v1/me/switch-school", ep.get("me_switch_school", ""))
        self.assertIn("/api/v1/tenants/children", ep.get("tenants_children", ""))
        self.assertIn("/api/v1/tenants/provision", ep.get("tenants_provision", ""))
        self.assertIn("/api/v1/tenants/", ep.get("tenants_modules", ""))
        self.assertIn("/modules", ep.get("tenants_modules", ""))
        self.assertIn("/api/v1/enrollment/apply", ep.get("enrollment_apply", ""))
        self.assertIn("/api/v1/enrollment/forecast", ep.get("enrollment_forecast", ""))
        self.assertIn("/api/v1/attendance/bulk", ep.get("attendance_bulk", ""))
        self.assertIn("/api/v1/attendance/export", ep.get("attendance_export", ""))
        self.assertIn("/api/v1/scheduler/validate", ep.get("scheduler_validate", ""))
        self.assertIn("/api/v1/syllabus/pacing", ep.get("syllabus_pacing", ""))
        self.assertIn("/api/v1/config/education-dna", ep.get("config_education_dna", ""))
        self.assertIn("/api/v1/config/education-templates", ep.get("config_education_templates", ""))
        self.assertIn("/api/v1/config/integration-catalog", ep.get("config_integration_catalog", ""))
        self.assertIn("/api/v1/config/risk-thresholds", ep.get("config_risk_thresholds", ""))
        self.assertIn("/api/v1/reports/scheduled", ep.get("reports_scheduled", ""))
        self.assertIn(
            "/api/v1/reports/regulatory-presets", ep.get("reports_regulatory_presets", "")
        )
        self.assertIn("/api/v1/reports/adhoc", ep.get("reports_adhoc", ""))
        self.assertIn("/api/v1/finance/disputes", ep.get("finance_disputes", ""))
        self.assertIn(
            "/api/v1/finance/wallet/top-up", ep.get("finance_wallet_top_up", "")
        )
        self.assertIn("/api/v1/intervention/red-flags", ep.get("intervention_red_flags", ""))
        self.assertIn("/api/v1/rosetta/scales", ep.get("rosetta_scales", ""))
        self.assertIn("/api/v1/super/pulse", ep.get("super_pulse", ""))
        self.assertIn("/api/v1/super/usage", ep.get("super_usage", ""))
        self.assertIn(
            "/api/v1/super/recovery-rate", ep.get("super_recovery_rate", "")
        )
        self.assertIn(
            "/api/v1/super/tenant-health", ep.get("super_tenant_health", "")
        )
        self.assertIn("/api/v1/super/schools", ep.get("super_schools_list", ""))
        self.assertIn(
            "/api/v1/compliance/export-school", ep.get("compliance_export_school", "")
        )
        self.assertIn("/api/v1/student/transfer", ep.get("student_transfer", ""))
        self.assertIn("/api/v1/rosetta/convert", ep.get("rosetta_convert", ""))
        self.assertIn(
            "/api/v1/reports/regulatory-export",
            ep.get("reports_regulatory_export", ""),
        )
        self.assertIn(
            "/api/v1/attendance/bulk-update",
            ep.get("attendance_bulk_update", ""),
        )
        self.assertIn(
            "/api/v1/intervention/action-center",
            ep.get("intervention_action_center", ""),
        )
        self.assertIn(
            "/api/v1/intervention/calculate-risk",
            ep.get("intervention_calculate_risk", ""),
        )
        self.assertIn(
            "/api/v1/student/passport/",
            ep.get("student_passport", ""),
        )
        self.assertIn("/api/v1/reports/emis/prepare", ep.get("reports_emis_prepare", ""))
        self.assertIn("/api/interop/edfi/", ep.get("interop_edfi", ""))
        self.assertIn("/api/interop/ceds/", ep.get("interop_ceds", ""))
        self.assertIn(
            "/api/interop/district-readiness/sample/",
            ep.get("interop_district_readiness_sample", ""),
        )
        self.assertIn(
            "/developers/api-docs/", data["endpoints"]["developer_public_api_doc"]
        )
        self.assertIn("lti", data)
        self.assertIn("plan_entitlements", data)
        pe = data.get("plan_entitlements") or {}
        self.assertIn("core", pe.get("tiers", {}))
        self.assertIn("report_platform_skus", pe)
        self.assertIn(
            "reports-standard",
            (pe.get("report_platform_skus") or {}).get("bundles", {}),
        )
        self.assertNotIn("operator_default_report_platform_bundle", pe)

    def test_manifest_curated_endpoints_align_with_reverse(self):
        from apps.api.api_v1_manifest import (
            MANIFEST_CURATED_API_V1_URL_NAMES,
            reverse_curated_api_v1_path,
        )

        r = self.client.get("/api/v1/manifest.json")
        self.assertEqual(r.status_code, 200)
        ep = r.json().get("endpoints") or {}
        for key, url_name in MANIFEST_CURATED_API_V1_URL_NAMES:
            self.assertIn(key, ep, msg=f"missing manifest key {key}")
            suffix = reverse_curated_api_v1_path(url_name)
            self.assertTrue(
                ep[key].replace("\\", "/").rstrip("/").endswith(suffix.rstrip("/")),
                msg=f"manifest[{key}]={ep[key]!r} does not end with reverse={suffix!r}",
            )

    def test_manifest_curated_url_names_subset_of_api_v1_named_routes_snapshot(self):
        """Curated integrator endpoints must exist in the gated urlpattern name list (batch 5 #42)."""
        from apps.api.api_v1_manifest import MANIFEST_CURATED_API_V1_URL_NAMES

        snap = Path(settings.BASE_DIR) / "scripts" / "generated" / "api_v1_named_routes.json"
        self.assertTrue(snap.is_file(), msg=f"missing snapshot {snap}")
        payload = json.loads(snap.read_text(encoding="utf-8"))
        names = set(payload.get("names") or [])
        for key, url_name in MANIFEST_CURATED_API_V1_URL_NAMES:
            self.assertIn(
                url_name,
                names,
                msg=(
                    f"curated manifest references api_v1:{url_name} ({key!r}) "
                    f"but that name is not in {snap}; refresh snapshot with "
                    f"python scripts/verify_api_v1_named_routes_snapshot.py --write"
                ),
            )

    def test_api_v1_non_curated_route_names_file_matches_snapshot(self):
        """Appendix JSON: all snapshot names not listed in MANIFEST_CURATED_* (batch 3 #24)."""
        from apps.api.api_v1_manifest import MANIFEST_CURATED_API_V1_URL_NAMES

        snap = Path(settings.BASE_DIR) / "scripts" / "generated" / "api_v1_named_routes.json"
        appendix = (
            Path(settings.BASE_DIR)
            / "scripts"
            / "generated"
            / "api_v1_non_curated_route_names.json"
        )
        self.assertTrue(snap.is_file(), msg=f"missing snapshot {snap}")
        self.assertTrue(appendix.is_file(), msg=f"missing {appendix}; run verify script --write")
        curated = {u for _k, u in MANIFEST_CURATED_API_V1_URL_NAMES}
        names = json.loads(snap.read_text(encoding="utf-8")).get("names") or []
        expected = sorted(n for n in names if n not in curated)
        blob = json.loads(appendix.read_text(encoding="utf-8"))
        self.assertEqual(blob.get("non_curated"), expected)

    def test_manifest_plan_entitlements_operator_default_from_singleton(self):
        from apps.platform_runtime.models import PlatformReportPlatformSkuDefault

        PlatformReportPlatformSkuDefault.objects.create(
            pk=1, default_bundle_slug="reports-standard"
        )
        r = self.client.get("/api/v1/manifest.json")
        self.assertEqual(r.status_code, 200)
        pe = r.json().get("plan_entitlements") or {}
        self.assertEqual(
            pe.get("operator_default_report_platform_bundle"), "reports-standard"
        )
