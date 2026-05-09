"""Tests for tenant_purge and rotate_audit_hmac_key commands."""

from __future__ import annotations

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.schools.models import School


class TenantPurgeCommandTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            slug="purge-target-test",
            name="Purge Target",
            country_code="CM",
            is_active=True,
        )

    def test_missing_school_arg_errors(self):
        with self.assertRaises(CommandError):
            call_command("tenant_purge", "--confirm-delete-string=x")

    def test_confirm_string_must_match_slug(self):
        with self.assertRaises(CommandError):
            call_command(
                "tenant_purge",
                f"--school={self.school.slug}",
                "--confirm-delete-string=wrong-slug",
            )

    def test_unknown_slug_errors(self):
        with self.assertRaises(CommandError):
            call_command(
                "tenant_purge",
                "--school=does-not-exist",
                "--confirm-delete-string=does-not-exist",
            )

    def test_dry_run_does_not_delete(self):
        out = StringIO()
        call_command(
            "tenant_purge",
            f"--school={self.school.slug}",
            f"--confirm-delete-string={self.school.slug}",
            stdout=out,
        )
        self.assertIn("DRY-RUN", out.getvalue())
        self.assertTrue(
            School.objects.filter(slug=self.school.slug).exists(),
            "dry-run should not delete",
        )


class RotateAuditHmacKeyTests(TestCase):
    def test_dry_run_prints_key_and_kid(self):
        out = StringIO()
        call_command("rotate_audit_hmac_key", "--kid=v_unit", "--dry-run", stdout=out)
        text = out.getvalue()
        self.assertIn("kid=v_unit", text)
        self.assertIn("AUDIT_HMAC_KEY_V_UNIT=", text)
        self.assertIn("DRY-RUN", text)

    def test_default_kid_is_timestamp(self):
        out = StringIO()
        call_command("rotate_audit_hmac_key", "--dry-run", stdout=out)
        text = out.getvalue()
        # Default kid starts with "v" + year prefix.
        self.assertIn("kid=v202", text)

    def test_apply_records_event_when_audit_log_present(self):
        try:
            from apps.compliance.models import AuditLog  # type: ignore
        except Exception:
            self.skipTest("AuditLog model not present in this environment.")
        before = AuditLog.objects.filter(action="audit.hmac_key_rotated").count()
        out = StringIO()
        call_command(
            "rotate_audit_hmac_key", "--kid=v_apply_unit", "--apply", stdout=out
        )
        after = AuditLog.objects.filter(action="audit.hmac_key_rotated").count()
        self.assertEqual(after - before, 1)
        self.assertIn("Rotation event recorded", out.getvalue())
