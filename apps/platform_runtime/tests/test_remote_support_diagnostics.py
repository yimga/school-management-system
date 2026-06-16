"""Remote Support P3 — diagnostics snapshot (no DB)."""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.platform_runtime import remote_support_diagnostics as diag
from apps.platform_runtime.jit_operator_controller import (
    _OPERATOR_FORBIDDEN_FIELDS,
)
from apps.platform_runtime.models_remote_support import RemoteSupportSession


class _School:
    id = 1
    name = "Test High"
    slug = "test-high"
    school_type = "secondary"
    country_code = "US"
    plan_id = None
    is_active = True
    features = {"offline_mode": True}
    settings = {
        "provisioning": {
            "phase_a_complete": True,
            "phase_b_complete": False,
            "phase_b_failed_steps": ["terms"],
        }
    }


def _all_keys(d, acc=None):
    acc = acc if acc is not None else set()
    for k, v in d.items():
        acc.add(k)
        if isinstance(v, dict):
            _all_keys(v, acc)
    return acc


class DiagnosticSnapshotTests(SimpleTestCase):
    def test_snapshot_has_all_sections(self):
        snap = diag.build_diagnostic_snapshot(school=_School(), now_iso="t0")
        for key in (
            "captured_at",
            "school",
            "deployment",
            "provisioning",
            "health",
            "offline_queue",
        ):
            self.assertIn(key, snap)
        self.assertEqual(snap["captured_at"], "t0")

    def test_school_identity_captured(self):
        snap = diag.build_diagnostic_snapshot(school=_School())
        self.assertEqual(snap["school"]["name"], "Test High")
        self.assertEqual(snap["school"]["slug"], "test-high")

    def test_deployment_offline_flag(self):
        snap = diag.build_diagnostic_snapshot(school=_School())
        self.assertTrue(snap["deployment"]["offline_mode"])

    def test_provisioning_reflects_settings(self):
        snap = diag.build_diagnostic_snapshot(school=_School())
        self.assertTrue(snap["provisioning"]["phase_a_complete"])
        self.assertFalse(snap["provisioning"]["phase_b_complete"])
        self.assertEqual(
            snap["provisioning"]["phase_b_failed_steps"], ["terms"]
        )

    def test_snapshot_is_pii_free(self):
        snap = diag.build_diagnostic_snapshot(school=_School())
        keys = _all_keys(snap)
        leaked = keys & set(_OPERATOR_FORBIDDEN_FIELDS)
        self.assertEqual(leaked, set(), f"diagnostics leaked PII keys: {leaked}")

    def test_query_sections_degrade_gracefully(self):
        # No DB available -> health/offline_queue come back as None, not errors.
        snap = diag.build_diagnostic_snapshot(school=_School())
        self.assertIsNone(snap["health"]["score"])
        self.assertIsNone(snap["offline_queue"]["pending"])


class AttachDiagnosticsTests(SimpleTestCase):
    @mock.patch.object(RemoteSupportSession, "record_lifecycle_audit")
    @mock.patch.object(RemoteSupportSession, "save")
    def test_attach_sets_and_audits(self, save, audit):
        session = RemoteSupportSession(school_id=1)
        diag.attach_diagnostics(session=session, snapshot={"a": 1})
        self.assertEqual(session.diagnostics, {"a": 1})
        self.assertTrue(save.called)
        self.assertTrue(audit.called)
