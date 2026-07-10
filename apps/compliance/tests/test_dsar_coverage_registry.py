"""DSAR coverage-registry guardrail tests (apps.compliance.dsar_registry).

Two jobs:

1. **Completeness guardrail** — introspect the live models in the data-subject
   home apps (``people``, ``accounts``) and fail loudly if any PII-bearing model
   is UNCLASSIFIED, i.e. added without an exporter/eraser or a documented
   exemption. ``test_guardrail_trips_on_unregistered_pii_model`` proves the check
   is not vacuous by trimming the registry and watching a known subject fall into
   the unclassified bucket.
2. **Producer/applier liveness** — every dotted path the registry names for
   export / erase must import to a callable, and every exemption must carry a
   reason + legal basis, so the registry can never drift into referencing a dead
   function or a silent carve-out.

Plus a behavioural proof that the newly-wired RELATED_ERASED model
(``people.BadgeScanEvent``) is genuinely scrubbed by the student + staff erasers.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.test import TestCase
from django.utils.module_loading import import_string

from apps.accounts.models import User
from apps.compliance import dsar_registry as reg
from apps.compliance.dsar_subjects import gdpr_scrub_staff
from apps.compliance.gdpr_services import gdpr_scrub_student
from apps.people.models import BadgeScanEvent, StudentProfile, TeacherProfile
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig


class DsarCoverageRegistryTests(TestCase):
    def test_no_unclassified_pii_models(self):
        """Every PII-bearing model in scope is classified (subject/related/exempt)."""
        report = reg.build_coverage_report()
        unclassified = report["unclassified"]
        self.assertEqual(
            unclassified,
            [],
            msg=(
                "PII-bearing model(s) escaped DSAR coverage: "
                + ", ".join(
                    f"{u['label']} (fields: {', '.join(u['pii_fields'])})"
                    for u in unclassified
                )
                + ". Wire an exporter+eraser (add to DSAR_SUBJECT_MODELS or "
                "DSAR_RELATED_ERASED_MODELS) OR record a documented exemption in "
                "DSAR_EXEMPT_MODELS in apps/compliance/dsar_registry.py."
            ),
        )

    def test_scan_actually_finds_the_known_subjects(self):
        """Sanity: the scanner is live — it detects the core subject models."""
        found = {label for label, _ in reg.iter_pii_bearing_models()}
        for label in (
            "people.StudentProfile",
            "people.TeacherProfile",
            "people.StudentGuardian",
            "people.Applicant",
            "accounts.User",
        ):
            self.assertIn(label, found)

    def test_guardrail_trips_on_unregistered_pii_model(self):
        """Removing a subject from the registry surfaces it as unclassified.

        Proves the completeness check genuinely fails when a PII model is not
        covered — i.e. it would catch a newly-added PII model.
        """
        trimmed = dict(reg.DSAR_SUBJECT_MODELS)
        trimmed.pop("people.StudentProfile")
        report = reg.build_coverage_report(subjects=trimmed)
        labels = {u["label"] for u in report["unclassified"]}
        self.assertIn("people.StudentProfile", labels)

    def test_registered_subject_producers_import_and_are_callable(self):
        for label, spec in reg.DSAR_SUBJECT_MODELS.items():
            for kind in ("export", "erase"):
                path = spec.get(kind)
                if path is None:
                    continue
                fn = import_string(path)
                self.assertTrue(
                    callable(fn), f"{label}.{kind} -> {path} is not callable"
                )

    def test_related_erased_appliers_import_and_are_callable(self):
        for label, spec in reg.DSAR_RELATED_ERASED_MODELS.items():
            for path in spec["erased_by"]:
                fn = import_string(path)
                self.assertTrue(
                    callable(fn), f"{label} erased_by {path} is not callable"
                )

    def test_cross_app_erased_labels_resolve_to_live_models(self):
        for label in reg.DSAR_CROSS_APP_ERASED:
            app_label, model_name = label.split(".")
            self.assertIsNotNone(
                django_apps.get_model(app_label, model_name),
                f"{label} in DSAR_CROSS_APP_ERASED no longer resolves",
            )

    def test_exemptions_carry_reason_and_legal_basis(self):
        self.assertTrue(reg.DSAR_EXEMPT_MODELS)
        for label, spec in reg.DSAR_EXEMPT_MODELS.items():
            self.assertTrue(spec.get("reason", "").strip(), f"{label} missing reason")
            self.assertTrue(
                spec.get("legal_basis", "").strip(), f"{label} missing legal_basis"
            )


class BadgeScanErasureTests(TestCase):
    """Behavioural proof the RELATED_ERASED wiring actually scrubs identifiers."""

    def setUp(self):
        self.region, _ = RegionConfig.objects.get_or_create(
            code="DCR",
            defaults={
                "name": "DSAR Coverage Reg",
                "default_language": "en",
                "timezone": "UTC",
                "date_format": "DD/MM/YYYY",
            },
        )
        self.school = School.objects.create(
            name="Badge School",
            slug="badge-school",
            subdomain="badge-school",
            is_active=True,
            default_region=self.region,
        )

    def test_student_erase_strips_badge_scan_pii(self):
        student_user = User.objects.create_user(
            username="badge_stu", email="stu@example.com", password="pw",
            role=User.Role.STUDENT,
        )
        student = StudentProfile.objects.create(
            school=self.school,
            user=student_user,
            first_name="Sam",
            last_name="Scan",
            student_code="BDG-STU-1",
        )
        scan = BadgeScanEvent.objects.create(
            token_kind=BadgeScanEvent.KIND_STUDENT,
            student=student,
            ip_address="203.0.113.9",
            user_agent="Mozilla/5.0 (scan gate)",
            notes="Entered via north gate",
        )
        result = gdpr_scrub_student(self.school.id, student.id)
        self.assertTrue(result["ok"], result)
        scan.refresh_from_db()
        self.assertIsNone(scan.ip_address)
        self.assertEqual(scan.user_agent, "")
        self.assertEqual(scan.notes, "")
        # Row preserved (non-PII attendance signal kept).
        self.assertTrue(BadgeScanEvent.objects.filter(pk=scan.pk).exists())

    def test_staff_erase_strips_badge_scan_pii(self):
        teacher_user = User.objects.create_user(
            username="badge_stf", email="stf@example.com", password="pw",
            role=User.Role.TEACHER,
        )
        TeacherProfile.objects.create(
            school=self.school, user=teacher_user, staff_id="STF-BDG", phone="555-1",
        )
        scan = BadgeScanEvent.objects.create(
            token_kind=BadgeScanEvent.KIND_STAFF,
            user=teacher_user,
            ip_address="203.0.113.11",
            user_agent="Mozilla/5.0 (staff gate)",
            notes="Clocked in",
        )
        result = gdpr_scrub_staff(self.school.id, teacher_user.id)
        self.assertTrue(result["ok"], result)
        scan.refresh_from_db()
        self.assertIsNone(scan.ip_address)
        self.assertEqual(scan.user_agent, "")
        self.assertEqual(scan.notes, "")
