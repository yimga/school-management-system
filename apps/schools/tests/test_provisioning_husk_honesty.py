"""Provisioned != usable: a husk must never self-report ready, and activation
must refuse a schema-less tenant.

The husk case (is_active default-True but no tenant tables) is only PROVABLE on
Postgres schema mode; on SQLite/RLS the probe is unknowable (None). These tests
simulate the production husk by patching ``tenant_workspace_exists`` to return
False, then assert the honest behavior — MUST-FIRE, not just must-not-flag.
"""
from __future__ import annotations

import uuid
from unittest import mock

from django.test import TestCase

from apps.schools.models import School
from apps.schools.provisioning_progress import (
    resolve_portal_ready,
    resolve_provisioning_progress,
)
from apps.schools.tasks import _activate_portal_phase_a

_PROBE = "apps.schools.tenant_workspace.tenant_workspace_exists"


def _school(active=True):
    slug = f"husk-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name="Husk", slug=slug, subdomain=slug, is_active=active
    )


class HuskProgressHonestyTests(TestCase):
    """G2 — the owner poll must not lie for a provably-absent (husk) tenant."""

    def test_husk_does_not_report_ready_or_complete(self):
        school = _school(active=True)
        with mock.patch(_PROBE, return_value=False):
            self.assertFalse(resolve_portal_ready(school))
            prog = resolve_provisioning_progress(school)
        self.assertNotEqual(prog["status"], "succeeded")
        self.assertFalse(prog["portal_ready"])
        self.assertTrue(prog["needs_resume"])
        self.assertLess(prog["progress_percent"], 100)
        self.assertNotIn("ready", (prog["phase_message"] or "").lower())

    def test_active_with_present_workspace_still_reports_ready(self):
        # Control: a genuinely-provisioned active school (probe True) is unchanged.
        school = _school(active=True)
        with mock.patch(_PROBE, return_value=True):
            self.assertTrue(resolve_portal_ready(school))
            prog = resolve_provisioning_progress(school)
        self.assertEqual(prog["status"], "succeeded")
        self.assertTrue(prog["portal_ready"])
        self.assertEqual(prog["progress_percent"], 100)

    def test_unknowable_workspace_is_not_treated_as_husk(self):
        # None (RLS/SQLite) must NOT collapse to absence — legacy active schools
        # and every local/test run stay "ready".
        school = _school(active=True)
        with mock.patch(_PROBE, return_value=None):
            prog = resolve_provisioning_progress(school)
        self.assertEqual(prog["status"], "succeeded")
        self.assertTrue(prog["portal_ready"])


class ActivatePostConditionTests(TestCase):
    """G4 — _activate_portal_phase_a must refuse a schema-less tenant."""

    def test_refuses_to_activate_when_workspace_provably_absent(self):
        school = _school(active=False)
        with mock.patch(_PROBE, return_value=False):
            with self.assertRaises(RuntimeError):
                _activate_portal_phase_a(
                    school,
                    school_id=str(school.pk),
                    contact_email="owner@example.com",
                    admin_user=None,
                    wf_run=None,
                    pulse=lambda *a, **k: None,
                )
        school.refresh_from_db()
        self.assertFalse(school.is_active)

    def test_unknowable_probe_does_not_block_activation_guard(self):
        # None must pass the guard (no raise from the probe branch). We stop the
        # heavy downstream activation work right after the guard by patching the
        # settings-merge to raise a sentinel — proving the guard itself let None
        # through rather than blocking it.
        school = _school(active=False)
        sentinel = RuntimeError("reached-past-guard")
        with mock.patch(_PROBE, return_value=None), mock.patch(
            "apps.schools.tasks._merge_provisioning_settings", side_effect=sentinel
        ):
            with self.assertRaises(RuntimeError) as ctx:
                _activate_portal_phase_a(
                    school,
                    school_id=str(school.pk),
                    contact_email="owner@example.com",
                    admin_user=None,
                    wf_run=None,
                    pulse=lambda *a, **k: None,
                )
        self.assertIn("reached-past-guard", str(ctx.exception))
