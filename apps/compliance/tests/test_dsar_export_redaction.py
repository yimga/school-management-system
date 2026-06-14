"""WF14 (DSAR) — Art.15/Art.20 export routes through DLP + emits an audit log.

Plain ``unittest`` (no DB) so it runs even where the Django test runner can't.

Guards the 2026-06-10 change: export_student_data_portability now passes every
section through apps.policies.dlp.redact_record (action="export", keyed by the
data subject) so third-party Personal Data is masked per the field catalog's
sensitivity tiers, and emits one PolicyDecisionLog row per export. Previously the
export bypassed the DLP layer entirely (third-party masking was operator-manual).
"""

from __future__ import annotations

import inspect
import os
import unittest

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()


class DsarExportRedactionTests(unittest.TestCase):

    def test_export_source_routes_sections_through_redact(self) -> None:
        from apps.compliance import gdpr_services

        src = inspect.getsource(gdpr_services.export_student_data_portability)
        # Every section is redacted via the shared helper, and the audit row is emitted.
        for section in (
            'entity="student"',
            'entity="person"',
            'entity="grade"',
            'entity="attendance"',
            'entity="incident"',
            'entity="invoice"',
            'entity="payment"',
        ):
            self.assertIn(section, src, f"export missing redaction for {section}")
        self.assertIn("_log_dsar_export(", src)
        # The payload must use the redacted student core, not the raw one.
        self.assertIn('"student": student_core', src)

    def test_redact_helper_uses_export_action_and_subject(self) -> None:
        from apps.compliance import gdpr_services

        helper_src = inspect.getsource(gdpr_services._redact_export_rows)
        self.assertIn("redact_record(", helper_src)
        self.assertIn('action="export"', helper_src)
        # Fails open (never crashes the export) per DSAR runbook s7 backstop.
        self.assertIn("out.append(row)", helper_src)

    def test_audit_log_helper_emits_policy_decision_log(self) -> None:
        from apps.compliance import gdpr_services

        log_src = inspect.getsource(gdpr_services._log_dsar_export)
        self.assertIn("PolicyDecisionLog.objects.create(", log_src)
        self.assertIn('action="dsar_access_export"', log_src)
        self.assertIn('effect="allow"', log_src)

    def test_redact_record_and_pdp_symbols_exist(self) -> None:
        # The wired-in symbols must resolve (no phantom imports).
        from apps.policies.dlp import redact_record  # noqa: F401
        from apps.policies.pdp import PolicyDecisionLog

        names = {f.name for f in PolicyDecisionLog._meta.get_fields()}
        for f in ("action", "resource_type", "resource_id", "effect", "subject_id"):
            self.assertIn(f, names)


if __name__ == "__main__":
    unittest.main()
