"""Tenant post-import orchestrator + bundle resolution by school slug."""

from __future__ import annotations

import uuid

from django.test import TestCase
from django.utils import timezone

from apps.migration_cloud.models import IntakeMethod, MigrationBundle
from apps.migration_cloud.quarantine_resolution import resolve_latest_bundle_for_school
from apps.schools.models import School


def _school(tag: str) -> School:
    slug = f"{tag}-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=f"School {slug}",
        slug=slug,
        subdomain=slug,
        country_code="CM",
    )


class ResolveLatestBundleForSchoolTests(TestCase):
    def test_returns_newest_bundle_by_updated_at(self):
        school = _school("bundle-resolve")
        MigrationBundle.objects.create(
            school=school,
            label="older",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"older-{uuid.uuid4().hex}",
        )
        newer = MigrationBundle.objects.create(
            school=school,
            label="newer",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"newer-{uuid.uuid4().hex}",
        )
        MigrationBundle.objects.filter(pk=newer.pk).update(
            updated_at=timezone.now()
        )
        resolved = resolve_latest_bundle_for_school(school.slug)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.pk, newer.pk)

    def test_unknown_slug_returns_none(self):
        self.assertIsNone(resolve_latest_bundle_for_school("no-such-school-slug"))
