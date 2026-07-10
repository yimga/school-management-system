"""Athletics GDPR wiring — Art.20 export + Art.17 erasure, plus compliance weave.

``athletics_export_sections`` assembles the athlete's memberships / medical /
consent for the portability export; ``athletics_scrub_student`` redacts medical
notes + guardian PII IN PLACE while PRESERVING every row (FKs intact for
audit/eligibility history). The compliance app weaves both in.
"""

from __future__ import annotations

from django.test import RequestFactory

from apps.athletics.models import (
    MedicalClearance,
    ParticipationConsent,
    TeamMembership,
)
from apps.athletics.services.gdpr import (
    athletics_export_sections,
    athletics_scrub_student,
)
from apps.athletics.tests.base import BaseAthleticsTestCase


class AthleticsExportTests(BaseAthleticsTestCase):
    def setUp(self):
        super().setUp()
        self.membership = self.add_member(
            self.fx, status=TeamMembership.Status.PENDING
        )
        self.clearance = self.make_clearance(self.fx)
        _raw, self.consent = ParticipationConsent.mint(
            membership=self.membership,
            guardian_name="Jane Guardian",
            guardian_email="jane.guardian@example.com",
            consent_text="I consent.",
        )

    def test_export_sections_include_all_three(self):
        sections = athletics_export_sections(
            school_id=self.fx.school.pk, student_id=self.fx.student.pk
        )
        self.assertEqual(len(sections["team_memberships"]), 1)
        self.assertEqual(len(sections["medical_clearances"]), 1)
        self.assertEqual(len(sections["participation_consents"]), 1)
        # Guardian PII rides the export; the token sha256 does NOT.
        consent_row = sections["participation_consents"][0]
        self.assertEqual(consent_row["guardian_name"], "Jane Guardian")
        self.assertNotIn("token_sha256", consent_row)
        # The medical notes ride the export.
        self.assertIn("notes", sections["medical_clearances"][0])

    def test_export_is_student_scoped(self):
        # A different student in the same school has no athletics records.
        from apps.people.models import StudentProfile

        other = StudentProfile.objects.create(
            school=self.fx.school, first_name="Other", last_name="Kid",
            admission_number="ADM-a-other",
        )
        sections = athletics_export_sections(
            school_id=self.fx.school.pk, student_id=other.pk
        )
        self.assertEqual(sections["team_memberships"], [])
        self.assertEqual(sections["participation_consents"], [])


class AthleticsScrubTests(BaseAthleticsTestCase):
    def setUp(self):
        super().setUp()
        self.membership = self.add_member(
            self.fx, status=TeamMembership.Status.PENDING
        )
        self.clearance = self.make_clearance(self.fx)
        _raw, self.consent = ParticipationConsent.mint(
            membership=self.membership,
            guardian_name="Jane Guardian",
            guardian_email="jane.guardian@example.com",
            consent_text="I consent.",
        )

    def test_scrub_redacts_pii_but_preserves_rows(self):
        summary = athletics_scrub_student(
            school_id=self.fx.school.pk, student_id=self.fx.student.pk
        )
        self.assertEqual(summary["medical_clearances"], 1)
        self.assertEqual(summary["participation_consents"], 1)
        # Rows still exist ...
        self.assertTrue(MedicalClearance.objects.filter(pk=self.clearance.pk).exists())
        self.assertTrue(ParticipationConsent.objects.filter(pk=self.consent.pk).exists())
        # ... but PII is blanked / redacted.
        self.clearance.refresh_from_db()
        self.consent.refresh_from_db()
        self.assertEqual(self.clearance.notes, "")
        self.assertEqual(self.consent.guardian_name, "[erased]")
        self.assertEqual(self.consent.guardian_email, "")
        # Membership (non-sensitive) is preserved untouched.
        self.assertTrue(TeamMembership.objects.filter(pk=self.membership.pk).exists())

    def test_scrub_blanks_decision_ip_and_ua_retains_consent_proof(self):
        # Decide the consent through a request so the IP + user-agent are stamped.
        request = RequestFactory().post(
            "/athletics/consent/decide/",
            REMOTE_ADDR="203.0.113.7", HTTP_USER_AGENT="RegressionUA/1.0",
        )
        self.consent.consent(request)
        self.consent.refresh_from_db()
        self.assertEqual(self.consent.ip_address_decision, "203.0.113.7")
        self.assertEqual(self.consent.user_agent_decision, "RegressionUA/1.0")
        # Capture the consent-text proof (must be RETAINED across erasure).
        sha_before = self.consent.consent_text_sha256
        version_before = self.consent.consent_text_version
        self.assertTrue(sha_before)

        athletics_scrub_student(
            school_id=self.fx.school.pk, student_id=self.fx.student.pk
        )
        self.consent.refresh_from_db()
        # Decision IP + UA re-identify the guardian — both wiped.
        self.assertIsNone(self.consent.ip_address_decision)
        self.assertEqual(self.consent.user_agent_decision, "")
        # Guardian PII gone ...
        self.assertEqual(self.consent.guardian_name, "[erased]")
        self.assertEqual(self.consent.guardian_email, "")
        # ... but the consent-text legal proof is RETAINED (non-PII evidence).
        self.assertEqual(self.consent.consent_text_sha256, sha_before)
        self.assertEqual(self.consent.consent_text_version, version_before)


class ComplianceWeaveTests(BaseAthleticsTestCase):
    def setUp(self):
        super().setUp()
        self.membership = self.add_member(
            self.fx, status=TeamMembership.Status.PENDING
        )
        self.make_clearance(self.fx)
        ParticipationConsent.mint(
            membership=self.membership,
            guardian_name="Jane Guardian",
            guardian_email="jane.guardian@example.com",
            consent_text="I consent.",
        )

    def test_portability_export_includes_athletics(self):
        from apps.compliance.gdpr_services import export_student_data_portability

        payload = export_student_data_portability(
            self.fx.school.pk, self.fx.student.pk, format="json"
        )
        self.assertIsNotNone(payload)
        self.assertIn("athletics", payload)
        self.assertGreaterEqual(
            len(payload["athletics"].get("team_memberships", [])), 1
        )

    def test_gdpr_scrub_student_runs(self):
        from apps.compliance.gdpr_services import gdpr_scrub_student

        result = gdpr_scrub_student(
            self.fx.school.pk, self.fx.student.pk, dry_run=False
        )
        self.assertIsInstance(result, dict)
        # The athletics rows are preserved with PII redacted.
        self.membership.refresh_from_db()
        self.assertTrue(
            TeamMembership.objects.filter(pk=self.membership.pk).exists()
        )
