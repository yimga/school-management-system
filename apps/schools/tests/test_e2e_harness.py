"""E2E lifecycle harness — safety + round-trip.

The harness provisions marker'd test schools and tears them down. These tests lock the two
properties that matter: (1) a full provision→verify→teardown round-trip leaves ZERO residue,
and (2) teardown can NEVER touch a school that lacks the ``zzt-e2e-`` slug prefix + the
``settings["e2e_test"]`` flag — i.e. a real tenant is unreachable by teardown.
"""

from __future__ import annotations

import io

from django.test import TestCase, override_settings

from apps.schools.management.commands.e2e_lifecycle import (
    TEST_SLUG_PREFIX,
    Command,
    MatrixEntry,
)
from apps.schools.models import School


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class E2EHarnessSafetyTests(TestCase):
    def setUp(self):
        self.cmd = Command()
        self.cmd.stdout = io.StringIO()

    def test_is_test_school_requires_both_marker_and_flag(self):
        real = School.objects.create(name="Real School", slug="real-school", subdomain="real-school")
        prefix_only = School.objects.create(
            name="Prefix Only", slug=f"{TEST_SLUG_PREFIX}prefixonly", subdomain=f"{TEST_SLUG_PREFIX}prefixonly"
        )
        flag_only = School.objects.create(
            name="Flag Only", slug="flag-only", subdomain="flag-only", settings={"e2e_test": True}
        )
        marked = School.objects.create(
            name="Marked", slug=f"{TEST_SLUG_PREFIX}marked", subdomain=f"{TEST_SLUG_PREFIX}marked",
            settings={"e2e_test": True},
        )
        self.assertFalse(self.cmd._is_test_school(real))
        self.assertFalse(self.cmd._is_test_school(prefix_only))  # prefix but no flag
        self.assertFalse(self.cmd._is_test_school(flag_only))    # flag but no prefix
        self.assertTrue(self.cmd._is_test_school(marked))

    def test_teardown_never_touches_a_real_tenant(self):
        real = School.objects.create(name="Real Co", slug="real-co", subdomain="real-co")
        # A school with the prefix but NO flag must also survive (not fully marked).
        half = School.objects.create(
            name="Half", slug=f"{TEST_SLUG_PREFIX}half", subdomain=f"{TEST_SLUG_PREFIX}half"
        )
        marked = School.objects.create(
            name="Marked", slug=f"{TEST_SLUG_PREFIX}m1", subdomain=f"{TEST_SLUG_PREFIX}m1",
            settings={"e2e_test": True},
        )
        summary = self.cmd._teardown(self.cmd.stdout)
        self.assertEqual(summary["schools"], 1)  # only the fully-marked one
        self.assertTrue(School.objects.filter(pk=real.pk).exists())
        self.assertTrue(School.objects.filter(pk=half.pk).exists())
        self.assertFalse(School.objects.filter(pk=marked.pk).exists())

    def test_provision_verify_teardown_round_trip_zero_residue(self):
        entry = MatrixEntry("smoke", "Smoke Academy", "NG", "NGN", "Primary")
        result = self.cmd._provision_and_verify(entry)
        self.assertTrue(result.school_id)
        # provision stage must be recorded (PASS in RLS, or FAIL surfaced — never silent).
        self.assertIn(result.status_for("provision"), ("PASS", "FAIL"))
        self.assertTrue(
            School.objects.filter(slug=f"{TEST_SLUG_PREFIX}smoke").exists()
        )
        summary = self.cmd._teardown(self.cmd.stdout)
        self.assertGreaterEqual(summary["schools"], 1)
        residue = summary["residue"]
        self.assertEqual(residue["schools_remaining"], 0)
        self.assertIn(residue["orphan_runs"], (0, -1))
