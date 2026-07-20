"""Migration Cloud tenant closeout — retry, progress errors, next_step_url, hints.

Locks the 100% repo-contained UX/ops closeout after P0–P2 burn-down:
host-aware companion next URLs, failed-advance visibility + retry POST,
quarantine / empty-file row hints, and plan-catalog entitlement seeding.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from apps.accounts.models import User
from apps.migration_cloud.models import BundleStatus, MigrationBundle
from apps.migration_cloud.views_tenant_upload import (
    TenantMigrationRetryAdvanceView,
    _progress_payload,
    _row_hint,
)
from apps.schools.models import School, SchoolMembership


class NextStepUrlTests(SimpleTestCase):
    def test_prefers_portal_namespace_when_request_matches(self):
        from apps.migration_cloud.companion_receiver import _next_step_url

        request = RequestFactory().get("/")
        request.resolver_match = SimpleNamespace(namespace="migration_cloud_portal")
        seen: list[str] = []

        def _rev(name, kwargs=None):
            seen.append(name)
            if name == "migration_cloud_portal:bundle_detail":
                return f"/portal/migration/{kwargs['bundle_id']}/"
            raise NoReverseMatch(name)

        with mock.patch("django.urls.reverse", side_effect=_rev):
            url = _next_step_url(42, request)
        self.assertEqual(url, "/portal/migration/42/")
        self.assertEqual(seen[0], "migration_cloud_portal:bundle_detail")

    def test_falls_back_to_connector_review(self):
        from apps.migration_cloud.companion_receiver import _next_step_url

        def _rev(name, kwargs=None):
            if name == "migration_cloud_connector:bundle-review":
                return f"/school/setup/migration-cloud/bundle/{kwargs['bundle_id']}/review/"
            raise NoReverseMatch(name)

        with mock.patch("django.urls.reverse", side_effect=_rev):
            url = _next_step_url(7, None)
        self.assertIn("/7/", url)
        self.assertIn("review", url)


class RowHintCloseoutTests(SimpleTestCase):
    def test_quarantine_reason_surfaces(self):
        art = SimpleNamespace(
            quarantined=True,
            quarantine_reason="Duplicate admission number",
            row_count=3,
            detected_format="csv",
        )
        self.assertEqual(_row_hint(art), "Duplicate admission number")

    def test_empty_zip_hint(self):
        art = SimpleNamespace(
            quarantined=False, row_count=0, detected_format="zip"
        )
        self.assertIn("ZIP", _row_hint(art))


class ProgressPayloadCloseoutTests(SimpleTestCase):
    def test_exposes_advance_error(self):
        bundle = SimpleNamespace(
            pk=9,
            status=BundleStatus.FAILED,
            size_summary={"error": "schema_name empty"},
            progress_snapshot={},
            artifacts=SimpleNamespace(all=lambda: []),
            get_status_display=lambda: "Failed",
        )
        with mock.patch(
            "apps.migration_cloud.progress.refresh_snapshot",
            side_effect=RuntimeError("skip"),
        ):
            payload = _progress_payload(bundle)
        self.assertTrue(payload["failed"])
        self.assertEqual(payload["advance_error"], "schema_name empty")


@override_settings(ALLOWED_HOSTS=["*"])
class TenantRetryAdvanceTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Retry School",
            slug="retry-mc-school",
            subdomain="retry-mc-school",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username="mc-retry-admin",
            password="x",
            role=User.Role.ADMIN,
            is_staff=False,
        )
        SchoolMembership.objects.create(
            user=self.admin,
            school=self.school,
            role=User.Role.ADMIN,
            is_school_owner=False,
            is_primary=True,
        )
        self.bundle = MigrationBundle.objects.create(
            school=self.school,
            idempotency_key="mc-retry-advance-0001",
            status=BundleStatus.FAILED,
            size_summary={"error": "advance boom"},
        )

    def _attach_messages(self, request):
        setattr(request, "session", "session")
        messages = FallbackStorage(request)
        setattr(request, "_messages", messages)

    @mock.patch("apps.migration_cloud.views_tenant_upload._advance")
    @mock.patch(
        "apps.migration_cloud.views_tenant_upload._connector_reverse",
        return_value="/school/setup/migration-cloud/1/review/",
    )
    @mock.patch(
        "apps.migration_cloud.views_tenant_upload._request_school",
    )
    @mock.patch(
        "apps.migration_cloud.views_tenant_upload._tenant_bundle_or_404",
    )
    def test_failed_bundle_retries_to_ingesting(
        self, mock_bundle, mock_school, _rev, mock_advance
    ):
        mock_school.return_value = self.school
        mock_bundle.return_value = self.bundle
        request = self.factory.post("/school/setup/migration-cloud/1/retry/")
        request.user = self.admin
        self._attach_messages(request)
        response = TenantMigrationRetryAdvanceView.as_view()(
            request, bundle_id=self.bundle.pk
        )
        self.assertEqual(response.status_code, 302)
        self.bundle.refresh_from_db()
        self.assertEqual(self.bundle.status, BundleStatus.INGESTING)
        self.assertNotIn("error", self.bundle.size_summary or {})
        mock_advance.assert_called_once_with(self.bundle.pk)

    def test_retry_route_declared(self):
        src = Path("apps/migration_cloud/urls_connectors.py").read_text(encoding="utf-8")
        self.assertIn("bundle-retry", src)
        self.assertIn("TenantMigrationRetryAdvanceView", src)
        url = reverse(
            "migration_cloud_connector:bundle-retry",
            kwargs={"bundle_id": 7},
            urlconf="config.tenant_urls",
        )
        self.assertTrue(url.endswith("/bundle/7/retry/"))


class TemplateCloseoutMarkers(SimpleTestCase):
    def test_review_template_has_retry_and_failure_copy(self):
        text = Path("templates/migration_cloud/connector/bundle_review.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("data-mc-retry-advance", text)
        self.assertIn("Detection needs another try", text)
        self.assertIn("advance_error", text)
        self.assertIn("quarantine_reason", text)

    def test_command_center_tip_mentions_inspect(self):
        text = Path("templates/migration_cloud/operator/command_center.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("inspect_migration_tenant", text)


class CatalogEntitlementCloseout(SimpleTestCase):
    def test_growing_and_above_include_migration_cloud(self):
        from apps.billing.management.commands.seed_subscription_catalog import (
            PLAN_CATALOG,
        )

        by_slug = {p["slug"]: p for p in PLAN_CATALOG}
        for slug in (
            "growing-school",
            "professional-school",
            "multi-campus",
            "enterprise-network",
            "district-ministry",
            "white-label",
            "sovereign-self-hosted",
        ):
            self.assertIn(
                "migration_cloud",
                by_slug[slug]["features"],
                msg=f"{slug} missing migration_cloud",
            )
        self.assertNotIn("migration_cloud", by_slug["free-starter"]["features"])
        self.assertNotIn("migration_cloud", by_slug["micro-school"]["features"])


class CommandCenterRunbookCloseout(SimpleTestCase):
    def test_docs_mention_inspect_migration_tenant(self):
        text = Path("docs/MIGRATION_CLOUD_COMMAND_CENTER.md").read_text(encoding="utf-8")
        self.assertIn("inspect_migration_tenant", text)
        self.assertIn("growing", text.lower())
