"""Review & Import HTTP E2E: post-import closure panels render on applied bundles."""

from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.views_tenant_upload import TenantMigrationReviewView
from apps.schools.models import School, SchoolMembership

_MOCK_REVERSE = mock.patch(
    "apps.migration_cloud.views_tenant_upload._connector_reverse",
    side_effect=lambda request, name, **kwargs: f"/mock/{name}/",
)


class BundleReviewClosurePanelsTests(TestCase):
    def setUp(self):
        slug = f"closure-review-{uuid.uuid4().hex[:8]}"
        self.school = School.objects.create(
            name="Closure Review School",
            slug=slug,
            subdomain=slug,
            country_code="CM",
            is_active=True,
            is_approved=True,
        )
        self.admin = User.objects.create_user(
            username=f"closure-admin-{uuid.uuid4().hex[:8]}",
            password="x",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.admin,
            school=self.school,
            role=User.Role.ADMIN,
            is_primary=True,
        )
        self.bundle = MigrationBundle.objects.create(
            school=self.school,
            label="applied-import",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"closure-{uuid.uuid4().hex}",
            status=BundleStatus.APPLIED,
            mapping_summary={"apply_totals": {"created": 3, "updated": 1}},
        )
        self.factory = RequestFactory()

    def _get_review(self):
        request = self.factory.get(
            "/school/setup/migration-cloud/bundle/review/",
            HTTP_SEC_FETCH_DEST="document",
        )
        request.user = self.admin
        request.school = self.school
        request.session = {}
        request._messages = FallbackStorage(request)
        return TenantMigrationReviewView.as_view()(request, bundle_id=self.bundle.pk)

    @_MOCK_REVERSE
    def test_applied_bundle_renders_all_closure_panels(self, _reverse):
        response = self._get_review()
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for marker in (
            "mc-closure-summary",
            "mc-catalog-inversion-heading",
            "mc-teaching-graph-heading",
            "mc-finance-ledger-heading",
            "mc-people-directory-heading",
        ):
            self.assertIn(marker, html, msg=f"missing panel marker {marker!r}")

    @_MOCK_REVERSE
    def test_build_context_populates_closure_summary(self, _reverse):
        request = self.factory.get("/review/")
        request.user = self.admin
        request.school = self.school
        context = TenantMigrationReviewView().build_context(request, self.bundle)
        self.assertIsNotNone(context.get("migration_closure_summary"))
        self.assertIsNotNone(context.get("catalog_inversion_readiness"))
        self.assertIsNotNone(context.get("teaching_graph_readiness"))
        self.assertIsNotNone(context.get("finance_ledger_readiness"))
        self.assertIsNotNone(context.get("people_directory_readiness"))
