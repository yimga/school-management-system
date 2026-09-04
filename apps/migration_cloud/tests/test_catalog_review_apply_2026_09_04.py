"""Catalog routing apply actions + classify shape override (batch 1838)."""

from __future__ import annotations

import uuid
from unittest import mock

from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, SimpleTestCase, TestCase

from apps.accounts.models import User
from apps.migration_cloud.catalog_preflight import persist_catalog_preflight
from apps.migration_cloud.classifiers.domain import classify_domain
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)
from apps.migration_cloud.ontology.catalog import all_synonyms
from apps.migration_cloud.views_tenant_upload import TenantMigrationReviewView
from apps.schools.models import School, SchoolMembership

_MOCK_REVERSE = mock.patch(
    "apps.migration_cloud.views_tenant_upload._connector_reverse",
    side_effect=lambda request, name, **kwargs: f"/mock/{name}/",
)
_MOCK_ADVANCE = mock.patch("apps.migration_cloud.views_tenant_upload._advance")


def _school(tag: str) -> School:
    slug = f"{tag}-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=f"School {slug}",
        slug=slug,
        subdomain=slug,
        country_code="CM",
        settings={"grading": {"curriculum_tracks": ["vocational_trade"]}},
        is_active=True,
        is_approved=True,
    )


class TrackSystemHeaderSynonymTests(SimpleTestCase):
    def test_learnerid_and_firstnames_map_to_student_fields(self):
        ext = {s.lower().replace("_", "") for s in all_synonyms("external_id", "students")}
        first = {s.lower().replace("_", "") for s in all_synonyms("first_name", "students")}
        self.assertIn("learnerid", ext)
        self.assertIn("firstnames", first)


class ClassifyDomainCatalogShapeTests(TestCase):
    def test_subject_shape_wins_over_specialties_filename(self):
        school = _school("shape-cls")
        bundle = MigrationBundle.objects.create(
            label="shape-cls",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"shape-cls-{uuid.uuid4().hex}",
            status=BundleStatus.MAPPED,
            school=school,
        )
        artifact = MigrationArtifact.objects.create(
            bundle=bundle,
            path_within_bundle="specialties_20260118.csv",
            filename="specialties_20260118.csv",
            detected_format=ArtifactFormat.CSV,
            byte_size=100,
            sha256="b" * 64,
            profile={
                "format": "csv",
                "columns": [
                    {"name": "TITLE", "normalized": "title", "samples": ["WORKSHOP"]},
                    {"name": "CATEGORY", "normalized": "category", "samples": ["Professional"]},
                    {"name": "COEF", "normalized": "coef", "samples": ["6"]},
                ],
            },
        )
        result = classify_domain(artifact=artifact)
        self.assertEqual(result["chosen"], "academics")


class CatalogReviewApplyHttpTests(TestCase):
    def setUp(self):
        self.school = _school("catalog-apply")
        self.admin = User.objects.create_user(
            username=f"catalog-admin-{uuid.uuid4().hex[:8]}",
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
            label="catalog-apply",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"catalog-apply-{uuid.uuid4().hex}",
            status=BundleStatus.MAPPED,
        )
        self.artifact = MigrationArtifact.objects.create(
            bundle=self.bundle,
            path_within_bundle="subjects.xlsx",
            filename="subjects.xlsx",
            detected_format=ArtifactFormat.XLSX,
            byte_size=200,
            sha256="c" * 64,
            assigned_domain="specialties",
            inferred_domain=[{"domain": "specialties", "confidence": 0.9}],
            profile={
                "format": "xlsx",
                "columns": [
                    {"name": "TITLE", "normalized": "title", "samples": ["OHADA"]},
                    {"name": "CATEGORY", "normalized": "category", "samples": ["Professional"]},
                    {"name": "COEF", "normalized": "coef", "samples": ["6"]},
                ],
            },
        )
        persist_catalog_preflight(self.bundle)
        self.factory = RequestFactory()

    def _post(self, data: dict):
        request = self.factory.post(
            "/school/setup/migration-cloud/bundle/review/",
            data,
            HTTP_SEC_FETCH_DEST="document",
        )
        request.user = self.admin
        request.school = self.school
        request.session = {}
        setattr(request, "_messages", FallbackStorage(request))
        view = TenantMigrationReviewView.as_view()
        with _MOCK_REVERSE, _MOCK_ADVANCE:
            return view(request, bundle_id=self.bundle.pk)

    def test_bulk_apply_catalog_recommendations_retags_and_syncs(self):
        request = self.factory.post(
            "/school/setup/migration-cloud/bundle/review/",
            {"action": "apply_catalog_recommendations"},
            HTTP_SEC_FETCH_DEST="document",
        )
        request.user = self.admin
        request.school = self.school
        request.session = {}
        setattr(request, "_messages", FallbackStorage(request))
        view = TenantMigrationReviewView.as_view()
        with _MOCK_REVERSE, _MOCK_ADVANCE:
            response = view(request, bundle_id=self.bundle.pk)
        self.assertEqual(response.status_code, 302)
        self.artifact.refresh_from_db()
        self.bundle.refresh_from_db()
        self.assertEqual(self.artifact.assigned_domain, "academics")
        operator = (self.bundle.discovery_summary or {}).get("operator_assigned_domains") or {}
        self.assertEqual(operator.get("subjects.xlsx"), "academics")
        msgs = [str(m) for m in get_messages(request)]
        self.assertTrue(any("Applied suggested" in m for m in msgs))

    def test_single_row_apply_catalog_recommendation(self):
        response = self._post(
            {
                "action": "apply_catalog_recommendation",
                "artifact_id": str(self.artifact.pk),
            }
        )
        self.assertEqual(response.status_code, 302)
        self.artifact.refresh_from_db()
        self.assertEqual(self.artifact.assigned_domain, "academics")

    def test_build_context_surfaces_catalog_fixable_count(self):
        request = self.factory.get(
            "/school/setup/migration-cloud/bundle/review/",
            HTTP_SEC_FETCH_DEST="document",
        )
        request.user = self.admin
        request.school = self.school
        with _MOCK_REVERSE:
            ctx = TenantMigrationReviewView().build_context(request, self.bundle)
        self.assertGreaterEqual(ctx.get("catalog_fixable_count") or 0, 1)
        row = next(r for r in ctx["artifact_rows"] if r["id"] == self.artifact.pk)
        self.assertTrue(row["catalog_fixable"])
        self.assertEqual(row["catalog_recommended"], "academics")
