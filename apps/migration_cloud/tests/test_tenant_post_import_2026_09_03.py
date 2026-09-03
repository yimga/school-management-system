"""Tenant post-import orchestrator + bundle resolution by school slug."""

from __future__ import annotations

import uuid
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
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

    def test_school_without_bundle_returns_none(self):
        school = _school("no-bundle")
        self.assertIsNone(resolve_latest_bundle_for_school(school.slug))


class SchoolSlugAliasResolutionTests(TestCase):
    @override_settings(TENANT_SLUG_LOOKUP_ALIASES={"gilead-tech": "gilead-school"})
    def test_gilead_tech_alias_resolves_gilead_school_slug(self):
        school = School.objects.create(
            name="Gilead Technical High School",
            slug="gilead-school",
            subdomain="gilead-school",
            country_code="CM",
        )
        from apps.migration_cloud.quarantine_resolution import resolve_school_from_slug

        resolved = resolve_school_from_slug("gilead-tech")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.pk, school.pk)

    def test_production_subdomain_gilead_tech_resolves(self):
        school = School.objects.create(
            name="Gilead Technical High School",
            slug="gilead-school",
            subdomain="gilead-tech",
            country_code="CM",
        )
        from apps.migration_cloud.quarantine_resolution import resolve_school_from_slug

        self.assertEqual(resolve_school_from_slug("gilead-tech").pk, school.pk)
        self.assertEqual(resolve_school_from_slug("gilead-school").pk, school.pk)

    @override_settings(TENANT_SLUG_LOOKUP_ALIASES={"gilead-tech": "gilead-school"})
    def test_gilead_tech_alias_resolves_latest_bundle(self):
        school = School.objects.create(
            name="Gilead Technical High School",
            slug="gilead-school",
            subdomain="gilead-tech",
            country_code="CM",
        )
        bundle = MigrationBundle.objects.create(
            school=school,
            label="gilead-import",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"gilead-{uuid.uuid4().hex}",
        )
        resolved = resolve_latest_bundle_for_school("gilead-tech")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.pk, bundle.pk)


class RemediateTenantPostImportNoBundleTests(TestCase):
    def test_dry_run_exits_clean_when_school_has_no_bundle(self):
        school = _school("no-bundle-orch")
        out = StringIO()
        call_command(
            "remediate_tenant_post_import",
            school=school.slug,
            dry_run=True,
            stdout=out,
        )
        rendered = out.getvalue()
        self.assertIn("quarantine preview skipped", rendered.lower())
        self.assertIn("Closure summary", rendered)


class RemediateTenantPostImportOrchestratorTests(TestCase):
    def test_dry_run_chains_five_steps_in_order(self):
        school = _school("orch-dry")
        calls: list[str] = []

        def _fake_call(command_name, *args, **kwargs):
            calls.append(command_name)
            return None

        out = StringIO()
        with patch(
            "apps.migration_cloud.management.commands.remediate_tenant_post_import.call_command",
            side_effect=_fake_call,
        ):
            call_command(
                "remediate_tenant_post_import",
                school=school.slug,
                dry_run=True,
                stdout=out,
            )

        self.assertEqual(
            calls,
            [
                "remediate_inverted_academic_catalog",
                "remediate_teaching_graph_closure",
                "remediate_people_directory",
                "remediate_finance_ledger_closure",
                "preview_quarantine_autopilot",
                "migration_closure_status",
            ],
        )
        rendered = out.getvalue()
        self.assertIn("1/5 academic catalog", rendered)
        self.assertIn("3/5 people directory", rendered)
        self.assertIn("5/5 quarantine autopilot", rendered)
        self.assertIn("Closure summary", rendered)

    def test_apply_chains_quarantine_batch(self):
        school = _school("orch-apply")
        calls: list[str] = []

        def _fake_call(command_name, *args, **kwargs):
            calls.append(command_name)
            return None

        with patch(
            "apps.migration_cloud.management.commands.remediate_tenant_post_import.call_command",
            side_effect=_fake_call,
        ):
            call_command(
                "remediate_tenant_post_import",
                school=school.slug,
                apply=True,
                max_sweeps=3,
            )

        self.assertEqual(calls[-2], "remediate_quarantine_batch")
        self.assertEqual(calls[-1], "migration_closure_status")
        self.assertEqual(len(calls), 6)
