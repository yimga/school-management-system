"""Ingestion-engine audit wave 2 (2026-07-31) — closes the previously-documented
lower-priority items:

  * F1 — EMAIL intake now extracts attachments (was a fail-fast stub).
  * F3 — alumni lands in the students wave (was catch-all wave 4).
  * F4 — access_intake fails fast (visible) when no table can be exported.
  * F5 — the command center now surfaces alert-status + concierge-source sections
    (both modules were built but had no production consumer).
  * F7 — self-serve upload validation warns (never silently) when no malware
    scanner is configured.

F2 (communications sent_at/status via DFV) and F6 (all-model phantom-field
coverage) are validated by the existing communications-lander tests and
``test_lander_phantom_fields_runtime_2026_07_31`` respectively.
"""

from __future__ import annotations

from email.message import EmailMessage
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from apps.migration_cloud.intake.base import IntakeContext, IntakeError


def _ctx() -> IntakeContext:
    return IntakeContext(bundle_id=1, idempotency_key="wave2-key")


class EmailIntakeTests(SimpleTestCase):
    """F1 — EMAIL intake extracts attachments (no longer a Phase-U7 stub)."""

    def _email_with_attachments(self, *attachments: tuple[str, bytes]) -> EmailMessage:
        msg = EmailMessage()
        msg["Subject"] = "Please migrate our roster"
        msg["From"] = "registrar@school.example"
        msg["To"] = "migrate@tenant.runmycampus.com"
        msg.set_content("Attached are the exports.")
        for name, data in attachments:
            msg.add_attachment(data, maintype="text", subtype="csv", filename=name)
        return msg

    def test_extracts_csv_attachment_as_artifact(self):
        from apps.migration_cloud.intake.email_intake import EmailIntakeAdapter

        msg = self._email_with_attachments(("students.csv", b"name,age\nAda,36\n"))
        adapter = EmailIntakeAdapter()
        adapter.validate_handle(msg, _ctx())  # must not raise
        payloads = list(adapter.iter_artifacts(msg, _ctx()))
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0].filename, "students.csv")
        with payloads[0].content_opener() as fh:
            self.assertIn(b"Ada", fh.read())

    def test_multiple_attachments_all_extracted(self):
        from apps.migration_cloud.intake.email_intake import EmailIntakeAdapter

        msg = self._email_with_attachments(
            ("students.csv", b"name\nAda\n"),
            ("staff.csv", b"name\nGrace\n"),
        )
        payloads = list(EmailIntakeAdapter().iter_artifacts(msg, _ctx()))
        self.assertEqual({p.filename for p in payloads}, {"students.csv", "staff.csv"})

    def test_no_attachments_fails_fast(self):
        msg = EmailMessage()
        msg["Subject"] = "no files"
        msg.set_content("I forgot to attach anything.")
        from apps.migration_cloud.intake.email_intake import EmailIntakeAdapter

        with self.assertRaises(IntakeError):
            EmailIntakeAdapter().validate_handle(msg, _ctx())

    def test_raw_bytes_handle_parsed(self):
        from apps.migration_cloud.intake.email_intake import EmailIntakeAdapter

        raw = self._email_with_attachments(("roster.csv", b"a,b\n1,2\n")).as_bytes()
        payloads = list(EmailIntakeAdapter().iter_artifacts(raw, _ctx()))
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0].filename, "roster.csv")


class AlumniWaveTests(SimpleTestCase):
    """F3 — alumni lands in the students root wave so children resolve its FKs."""

    def test_alumni_shares_the_students_wave(self):
        from apps.migration_cloud.orchestrator import _DEPENDENCY_WAVES

        students_wave = next(w for w in _DEPENDENCY_WAVES if "students" in w)
        self.assertIn("alumni", students_wave)


class AccessIntakeVisibilityTests(SimpleTestCase):
    """F4 — an Access DB whose tables all fail to export fails fast (visible)."""

    def test_all_tables_unexportable_raises(self):
        from apps.migration_cloud.intake import access_intake

        adapter = access_intake.AccessDbIntakeAdapter()
        with mock.patch.object(access_intake, "_list_tables", return_value=["t1", "t2"]), \
             mock.patch.object(access_intake, "_export_table_as_csv", return_value=b""):
            with self.assertRaises(IntakeError):
                list(adapter.iter_artifacts("/tmp/legacy.accdb", _ctx()))


class CommandCenterWiringTests(SimpleTestCase):
    """F5 — alert_status + source_adapters now have a live command-center consumer."""

    def test_alert_status_section_renders(self):
        from apps.migration_cloud.views_command_center import _section_alert_status

        sec = _section_alert_status()
        self.assertIsNone(sec.get("error"))
        self.assertIn("channels_enabled", sec)
        self.assertIn("dry_run", sec)

    def test_concierge_sources_section_renders_seeded_catalog(self):
        from apps.migration_cloud.views_command_center import _section_concierge_sources

        sec = _section_concierge_sources()
        self.assertIsNone(sec.get("error"))
        # The catalog is auto-seeded at import with the top competitor SIS specs.
        self.assertGreaterEqual(sec.get("source_count", 0), 1)


class MalwareScannerVisibilityTests(SimpleTestCase):
    """F7 — no configured scanner is a VISIBLE warning, not a silent skip."""

    @override_settings(UPLOAD_MALWARE_SCANNER=None)
    def test_unconfigured_scanner_warns_once(self):
        from apps.migration_cloud.services import intake_pipeline

        intake_pipeline._MALWARE_SCANNER_WARNED = False  # reset the one-time flag
        csv = SimpleUploadedFile(
            "students.csv", b"name,age\nAda,36\n", content_type="text/csv"
        )
        with self.assertLogs(
            "apps.migration_cloud.services.intake_pipeline", level="WARNING"
        ) as cm:
            intake_pipeline._validate_export_upload(csv)
        self.assertTrue(
            any("UPLOAD_MALWARE_SCANNER" in line for line in cm.output),
            cm.output,
        )
