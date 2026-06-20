"""Configure/Operate tail wizard domain writer tests (batch 3)."""

from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.academics.models import AcademicYear, Subject
from apps.compliance.models import ConsentRequest, NonRepudiationLogEntry
from apps.platform_runtime.models import RuntimeDefaults
from apps.registries.models import CountryRegistry
from apps.schools.models import School
from apps.setup_studio.wizard_resolvers import (
    write_comms_gateway,
    write_compliance_ledger,
    write_exam_window,
    write_fieldtrip_authorization,
    write_library_fines,
    write_pathway_matcher,
)


class CommsRoutingWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="US", defaults={"name": "United States"})
        self.school = School.objects.create(
            name="Comms School",
            slug="comms-school",
            subdomain="comms-school",
            country_code="US",
            is_active=True,
        )

    def test_gateway_priority_persisted(self):
        write_comms_gateway(
            school=self.school,
            wizard_key="omnichannel_communication_routing",
            step_key="gateway_prioritization",
            payload={"value": ["email", "sms", "whatsapp"]},
            actor_user_id=1,
        )
        self.school.refresh_from_db()
        routing = (self.school.settings or {}).get("communication_routing", {})
        self.assertEqual(routing.get("gateway_priority"), ["email", "sms", "whatsapp"])


class ComplianceLedgerWriterTests(TestCase):
    def test_ledger_anchor_platform_and_non_repudiation(self):
        User = get_user_model()
        user = User.objects.create_user(username="jit-op", password="x")
        write_compliance_ledger(
            school=None,
            wizard_key="jit_operator_compliance_safeguarding",
            step_key="ledger_immutable_endpoint",
            payload={"value": "append_only_db"},
            actor_user_id=user.pk,
        )
        rd = RuntimeDefaults.objects.get(pk=1)
        jit = (rd.payload or {}).get("jit_compliance", {})
        self.assertEqual(jit.get("ledger_anchor"), "append_only_db")
        self.assertTrue(
            NonRepudiationLogEntry.objects.filter(action="jit.ledger_anchor_selected").exists()
        )


class FieldTripWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Trip School",
            slug="trip-school",
            subdomain="trip-school",
            country_code="CM",
            is_active=True,
        )

    def test_authorization_creates_consent_request(self):
        write_fieldtrip_authorization(
            school=self.school,
            wizard_key="localized_field_trip_coordinator",
            step_key="automated_authorization_pipeline",
            payload={"parent_signature_required": True},
            actor_user_id=1,
        )
        self.assertTrue(
            ConsentRequest.objects.filter(
                school=self.school,
                category="field_trip",
            ).exists()
        )

    def test_authorization_consent_request_is_idempotent(self):
        # Re-running / editing the authorization step must NOT spawn a duplicate
        # consent request for the same trip — get_or_create keys on
        # (school, category, title).
        for _ in range(2):
            write_fieldtrip_authorization(
                school=self.school,
                wizard_key="localized_field_trip_coordinator",
                step_key="automated_authorization_pipeline",
                payload={"parent_signature_required": True},
                actor_user_id=1,
            )
        self.assertEqual(
            ConsentRequest.objects.filter(
                school=self.school,
                category="field_trip",
            ).count(),
            1,
        )


class LibraryWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="US", defaults={"name": "United States"})
        self.school = School.objects.create(
            name="Lib School",
            slug="lib-school",
            subdomain="lib-school",
            country_code="US",
            is_active=True,
        )

    def test_fine_policy_persisted(self):
        write_library_fines(
            school=self.school,
            wizard_key="library_inventory_management",
            step_key="fine_policy",
            payload={
                "fine_per_day_overdue_decimal": "1.00",
                "grace_period_days": 3,
                "max_fine_per_book_decimal": "15.00",
                "suspend_after_unpaid_fine_days": 14,
            },
            actor_user_id=1,
        )
        self.school.refresh_from_db()
        fines = (self.school.settings or {}).get("library", {}).get("fines", {})
        self.assertEqual(fines.get("fine_per_day_overdue_decimal"), "1.00")


class ExamWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Exam School",
            slug="exam-school",
            subdomain="exam-school",
            country_code="CM",
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )

    def test_exam_window_creates_session(self):
        from apps.academics.models import CertificationExamSession

        write_exam_window(
            school=self.school,
            wizard_key="exam_schedule_orchestration",
            step_key="exam_window_anchor",
            payload={
                "exam_window_label": "Midyear Exams 2026",
                "window_start_date": "2026-03-01",
                "window_end_date": "2026-03-15",
                "results_publish_date": "2026-03-20",
            },
            actor_user_id=1,
        )
        self.assertTrue(
            CertificationExamSession.objects.filter(
                school=self.school,
                name="Midyear Exams 2026",
            ).exists()
        )


class PathwayWriterTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="US", defaults={"name": "United States"})
        self.school = School.objects.create(
            name="Path School",
            slug="path-school",
            subdomain="path-school",
            country_code="US",
            is_active=True,
        )
        Subject.objects.create(school=self.school, name="Physics")

    def test_matcher_records_courses(self):
        write_pathway_matcher(
            school=self.school,
            wizard_key="personal_graduation_pathway_elective",
            step_key="dynamic_class_matcher",
            payload={"value": ["Physics", "UnknownCourse"]},
            actor_user_id=1,
        )
        self.school.refresh_from_db()
        matched = (self.school.settings or {}).get("graduation_pathway", {}).get("matched_courses", [])
        self.assertIn("Physics", matched)
