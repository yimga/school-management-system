"""Tests for inspect_migration_tenant + studio migration nav deep-link."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle


class InspectMigrationTenantCommandTests(TestCase):
    def test_missing_slug_errors(self):
        with self.assertRaises(CommandError):
            call_command("inspect_migration_tenant", stdout=StringIO())

    def test_unknown_school_errors(self):
        with self.assertRaises(CommandError):
            call_command(
                "inspect_migration_tenant",
                "--slug=no-such-school-xyz",
                stdout=StringIO(),
            )

    def test_lists_bundle_classification(self):
        from apps.schools.models import School

        school = School.objects.create(
            name="Inspect High",
            slug=f"inspect-{self.id()}",
            subdomain=f"inspect-{self.id()}",
        )
        MigrationBundle.objects.create(
            school=school,
            label="mapped empty schema",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"inspect-{self.id()}",
            status=BundleStatus.MAPPED,
            schema_name="",
        )
        out = StringIO()
        call_command(
            "inspect_migration_tenant",
            f"--slug={school.slug}",
            stdout=out,
        )
        text = out.getvalue()
        self.assertIn("mapped_awaiting_confirm_apply", text)
        self.assertIn(f"slug={school.slug}", text)


class StudioMigrationNavTests(SimpleTestCase):
    def test_redirect_targets_connector_upload(self):
        src = Path("apps/siteconfig/views_tenant_studio_hub.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("migration_cloud_connector:upload", src)
        self.assertIn("school_studio_redirect_migration", src)
