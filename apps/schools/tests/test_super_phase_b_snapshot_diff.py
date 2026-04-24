"""Phase B operator diff: live owned_payload vs materialized snapshot rows."""

import json
import re

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.platform_runtime.models import (
    PlatformOperatorPhaseBLink,
    PlatformPhaseBDomainSnapshot,
)
from apps.platform_runtime.phase_b_domain_snapshots import (
    PHASE_B_SNAPSHOT_DOMAINS,
    sync_phase_b_domain_snapshots_from_site,
)


@override_settings(ALLOWED_HOSTS=["*"])
class SuperPhaseBSnapshotDiffViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="phase_b_diff_tester",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)
        self.host = "manager.runmycampus.com"
        cache.clear()

    def test_phase_b_snapshot_diff_summary_table_headings_stable(self):
        """Batch 33 #415: HTML summary table thead must stay aligned with operator copy."""
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        url = reverse("super:phase_b_snapshot_diff")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        for label in (
            ">Domain</th>",
            ">Scope</th>",
            ">In sync</th>",
            ">Changed keys</th>",
            ">Live keys</th>",
            ">Stored keys</th>",
            ">Snapshot updated</th>",
            ">Actions</th>",
        ):
            self.assertIn(label, body)

    def test_phase_b_snapshot_diff_summary_domain_action_links_match_domain_count(self):
        """Batch 35 #445: summary tbody row cardinality tracks ``PHASE_B_SNAPSHOT_DOMAINS``."""
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        url = reverse("super:phase_b_snapshot_diff")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertEqual(
            body.count('href="?domain='),
            len(PHASE_B_SNAPSHOT_DOMAINS),
        )

    def test_phase_b_snapshot_diff_phase_h_skip_link_targets_main(self):
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        url = reverse("super:phase_b_snapshot_diff")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn('href="#phase-b-snapshot-diff-main"', body)
        self.assertIn('id="phase-b-snapshot-diff-main"', body)

    def test_phase_b_snapshot_diff_renders_operator_phase_b_curated_links(self):
        """Typed operator table ``PlatformOperatorPhaseBLink`` surfaces on diff hub (batch 23 #267)."""
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        PlatformOperatorPhaseBLink.objects.create(
            slug="batch-23-truth",
            label="Open runtime truth hub",
            href="/super/runtime-truth-hub/",
            sort_order=0,
        )
        url = reverse("super:phase_b_snapshot_diff")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Open runtime truth hub", body)
        self.assertIn('href="/super/runtime-truth-hub/"', body)

    def test_phase_b_export_json_v1_domain_row_key_order_matches_all_rows(self):
        """Drift guard: every ``domains[]`` object uses the same keys as the HTML/JSON contract (batch 23 #265)."""
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        url = reverse("super:phase_b_snapshot_diff")
        jresp = self.client.get(url + "?export=json", HTTP_HOST=self.host)
        data = json.loads(jresp.content.decode("utf-8"))
        expected_keys = [
            "domain",
            "operator_title",
            "operator_summary",
            "in_sync",
            "changed_key_count",
            "live_key_count",
            "stored_key_count",
            "live_checksum",
            "stored_checksum",
            "row_updated_at",
        ]
        domains = data.get("domains") or []
        self.assertEqual(len(domains), len(PHASE_B_SNAPSHOT_DOMAINS))
        for row in domains:
            self.assertEqual(
                list(row.keys()),
                expected_keys,
                msg=f"domain row key order drift: {row.get('domain')!r}",
            )

    def test_phase_b_snapshot_diff_renders_200(self):
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        url = reverse("super:phase_b_snapshot_diff")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Phase B snapshot diff", html=False)
        self.assertContains(response, "policies_rules", html=False)
        self.assertContains(response, "Report platform", html=False)
        self.assertContains(response, "Scope", html=False)

    def test_phase_b_snapshot_diff_export_action_buttons_present(self):
        """HTML export entry points stay wired when layout changes (batch 24 #280)."""
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        url = reverse("super:phase_b_snapshot_diff")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("export=json", body)
        self.assertIn("Export drift summary (JSON)", body)

    def test_phase_b_snapshot_diff_summary_table_headers_align_with_json_export_field_order(self):
        """Regression: thead labels match tbody columns and JSON `domains[]` key semantics (SOT batch 7 #65)."""
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        url = reverse("super:phase_b_snapshot_diff")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        thead_m = re.search(
            r'<thead class="table-light">\s*<tr>(.*?)</tr>\s*</thead>',
            body,
            re.DOTALL,
        )
        self.assertIsNotNone(thead_m, msg="summary table thead not found")
        raw_th = re.findall(r"<th[^>]*>(.*?)</th>", thead_m.group(1), flags=re.DOTALL)
        labels = [re.sub(r"<[^>]+>", "", t).strip() for t in raw_th]
        self.assertEqual(
            labels,
            [
                "Domain",
                "Scope",
                "In sync",
                "Changed keys",
                "Live keys",
                "Stored keys",
                "Snapshot updated",
                "Actions",
            ],
        )
        jresp = self.client.get(url + "?export=json", HTTP_HOST=self.host)
        data = json.loads(jresp.content.decode("utf-8"))
        row0 = (data.get("domains") or [{}])[0]
        self.assertEqual(
            list(row0.keys()),
            [
                "domain",
                "operator_title",
                "operator_summary",
                "in_sync",
                "changed_key_count",
                "live_key_count",
                "stored_key_count",
                "live_checksum",
                "stored_checksum",
                "row_updated_at",
            ],
        )

    def test_phase_b_snapshot_diff_summary_table_domain_column_order_matches_json_domains(
        self,
    ):
        """Tbody domain slugs align with ``domains[].domain`` order (batch 14 #140, narrower than thead #65)."""
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        url = reverse("super:phase_b_snapshot_diff")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        tbody_m = re.search(r"<tbody>(.*?)</tbody>", body, re.DOTALL)
        self.assertIsNotNone(tbody_m, msg="summary table tbody not found")
        domain_cells = re.findall(
            r"<tr[^>]*>\s*<td[^>]*>\s*<code[^>]*>([^<]+)</code>",
            tbody_m.group(1),
            re.DOTALL,
        )
        jresp = self.client.get(url + "?export=json", HTTP_HOST=self.host)
        data = json.loads(jresp.content.decode("utf-8"))
        json_domains = [row.get("domain") for row in (data.get("domains") or [])]
        self.assertEqual(domain_cells, json_domains)

    def test_phase_b_export_json_domain_order_matches_phase_b_snapshot_domains_constant(
        self,
    ):
        """Regression: HTML/JSON row order stays tied to ``PHASE_B_SNAPSHOT_DOMAINS`` (batch 15 #150)."""
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        url = reverse("super:phase_b_snapshot_diff") + "?export=json"
        data = json.loads(
            self.client.get(url, HTTP_HOST=self.host).content.decode("utf-8")
        )
        json_domains = [row.get("domain") for row in (data.get("domains") or [])]
        self.assertEqual(json_domains, list(PHASE_B_SNAPSHOT_DOMAINS))

    def test_phase_b_snapshot_diff_key_detail_html_lists_match_json_detail_export(self):
        """Key-diff card ``<code>`` keys match ``export=json&domain=`` ``key_detail`` (batch 14 #140)."""
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        row = PlatformPhaseBDomainSnapshot.objects.get(pk="documents")
        pl = dict(row.payload or {})
        pl["_html_json_detail_probe"] = "only-on-snapshot"
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
        base = reverse("super:phase_b_snapshot_diff")
        html_resp = self.client.get(base + "?domain=documents", HTTP_HOST=self.host)
        self.assertEqual(html_resp.status_code, 200)
        html = html_resp.content.decode("utf-8")

        def _codes_after(heading: str) -> set[str]:
            start = html.find(heading)
            self.assertGreaterEqual(start, 0, msg=f"missing heading {heading!r}")
            rest = html[start:]
            nxt = rest.find("<strong>", len(heading) + 2)
            chunk = rest[:nxt] if nxt != -1 else rest
            return set(re.findall(r"<code>([^<]+)</code>", chunk))

        json_resp = self.client.get(
            base + "?export=json&domain=documents", HTTP_HOST=self.host
        )
        self.assertEqual(json_resp.status_code, 200)
        kd = (json.loads(json_resp.content.decode("utf-8")).get("key_detail")) or {}

        self.assertEqual(
            _codes_after("Only on live"), set(kd.get("only_live") or [])
        )
        self.assertEqual(
            _codes_after("Only on snapshot row"), set(kd.get("only_stored") or [])
        )
        self.assertEqual(
            _codes_after("Same key, different value"),
            set(kd.get("value_mismatch") or []),
        )

    def test_phase_b_key_detail_section_headings_stable(self):
        """When UI adds columns elsewhere, key-detail card headings stay aligned with JSON contract (batch 17 #175 / batch 18 #190)."""
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        url = reverse("super:phase_b_snapshot_diff") + "?domain=documents"
        html = self.client.get(url, HTTP_HOST=self.host).content.decode("utf-8")
        for label in (
            "Only on live",
            "Only on snapshot row",
            "Same key, different value",
        ):
            self.assertIn(label, html, msg=f"missing key-detail heading {label!r}")

    def test_phase_b_snapshot_diff_shows_drift_when_snapshot_stale(self):
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        row = PlatformPhaseBDomainSnapshot.objects.get(pk="documents")
        pl = dict(row.payload or {})
        pl["_diff_probe"] = "stale-row-only"
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

        url = reverse("super:phase_b_snapshot_diff")
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "out of sync", html=False)

        detail = self.client.get(
            url + "?domain=documents",
            HTTP_HOST=self.host,
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "_diff_probe", html=False)

    def test_resync_post_materializes_from_live(self):
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        row = PlatformPhaseBDomainSnapshot.objects.get(pk="documents")
        pl = dict(row.payload or {})
        pl["_diff_probe"] = "stale-row-only"
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
        url = reverse("super:phase_b_snapshot_diff")
        response = self.client.post(
            url,
            {"action": "resync_all_snapshots"},
            HTTP_HOST=self.host,
        )
        self.assertEqual(response.status_code, 302)
        after = PlatformPhaseBDomainSnapshot.objects.get(pk="documents")
        self.assertNotIn("_diff_probe", after.payload or {})

    def test_phase_b_export_json_v2_detail_top_level_key_order_stable(self):
        """Batch 35 #445: v2 detail export keeps a stable top-level key contract."""
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        url = reverse("super:phase_b_snapshot_diff") + "?export=json&domain=documents"
        data = json.loads(
            self.client.get(url, HTTP_HOST=self.host).content.decode("utf-8")
        )
        self.assertEqual(data.get("export_version"), 2)
        self.assertEqual(
            list(data.keys()),
            [
                "export_version",
                "generated_at",
                "drift_count",
                "aggregate_checksum",
                "domains",
                "detail_domain",
                "key_detail",
                "unified_diff",
            ],
        )

    def test_phase_b_export_json_v1_top_level_key_order_stable(self):
        """Batch 34 #430: v1 export object key order stays aligned with HTML summary contract."""
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        url = reverse("super:phase_b_snapshot_diff") + "?export=json"
        data = json.loads(self.client.get(url, HTTP_HOST=self.host).content.decode("utf-8"))
        self.assertEqual(
            list(data.keys()),
            [
                "export_version",
                "generated_at",
                "drift_count",
                "aggregate_checksum",
                "domains",
            ],
        )

    def test_phase_b_snapshot_diff_export_json(self):
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        url = reverse("super:phase_b_snapshot_diff") + "?export=json"
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = json.loads(response.content.decode("utf-8"))
        self.assertEqual(data.get("export_version"), 1)
        self.assertIn("generated_at", data)
        self.assertIn("drift_count", data)
        self.assertIn("aggregate_checksum", data)
        self.assertEqual(len(data["aggregate_checksum"]), 64)
        self.assertIsInstance(data.get("domains"), list)
        self.assertGreaterEqual(len(data["domains"]), 1)
        first = data["domains"][0]
        self.assertIn("domain", first)
        self.assertIn("operator_title", first)
        self.assertIn("operator_summary", first)
        self.assertIn("in_sync", first)
        self.assertIn("live_checksum", first)
        self.assertIn("stored_checksum", first)
        self.assertIn("changed_key_count", first)
        self.assertIn("live_key_count", first)
        self.assertIn("stored_key_count", first)
        self.assertIn("row_updated_at", first)

    def test_phase_b_snapshot_diff_export_json_reflects_drift_count(self):
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        row = PlatformPhaseBDomainSnapshot.objects.get(pk="documents")
        pl = dict(row.payload or {})
        pl["_export_json_probe"] = "stale"
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
        url = reverse("super:phase_b_snapshot_diff") + "?export=json"
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode("utf-8"))
        self.assertGreaterEqual(data.get("drift_count", 0), 1)

    def test_phase_b_snapshot_diff_export_json_detail_domain_v2(self):
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        row = PlatformPhaseBDomainSnapshot.objects.get(pk="documents")
        pl = dict(row.payload or {})
        pl["_json_detail_probe"] = "only-on-snapshot"
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
        url = (
            reverse("super:phase_b_snapshot_diff")
            + "?export=json&domain=documents"
        )
        response = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode("utf-8"))
        self.assertEqual(data.get("export_version"), 2)
        self.assertIn("aggregate_checksum", data)
        self.assertEqual(data.get("detail_domain"), "documents")
        self.assertIn("domains", data)
        kd = data.get("key_detail") or {}
        self.assertIn("only_stored", kd)
        self.assertIn("_json_detail_probe", kd.get("only_stored", []))
        self.assertIn("unified_diff", data)
        self.assertIsInstance(data["unified_diff"], str)
        self.assertIn("_json_detail_probe", data["unified_diff"])

    def test_phase_b_export_json_v2_key_detail_top_level_schema_stable(self):
        """``key_detail`` keys stay aligned with ``diff_top_level_payload_keys`` (batch 16 #160)."""
        site = get_platform_site_settings_record(create=True)
        sync_phase_b_domain_snapshots_from_site(site)
        url = reverse("super:phase_b_snapshot_diff") + "?export=json&domain=documents"
        data = json.loads(
            self.client.get(url, HTTP_HOST=self.host).content.decode("utf-8")
        )
        self.assertEqual(data.get("export_version"), 2)
        kd = data.get("key_detail") or {}
        self.assertEqual(
            set(kd.keys()),
            {"only_live", "only_stored", "value_mismatch", "changed_key_count"},
        )
        for k in ("only_live", "only_stored", "value_mismatch"):
            self.assertIsInstance(kd[k], list)
        self.assertIsInstance(kd["changed_key_count"], int)
