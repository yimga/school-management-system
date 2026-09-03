"""Multi-strand signup, code prefix, and provision-log contract tests."""

from __future__ import annotations

import json
from datetime import date

from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.academics.structure_provisioning import (
    ensure_general_department,
    ensure_strand_specialties,
    provision_academic_structure_for_school,
)
from apps.schools.models import School, SchoolProvisioningEvent
from apps.test_utils.tenant_hosts import HOST_ROUTED_SETTINGS, public_client
from apps.schools.onboarding_strands import (
    canonicalize_strand_code,
    namespaced_structure_code,
    normalize_code_prefix,
    parse_operational_strands,
    resolve_provision_seed_inputs,
)
from apps.schools.provisioning_progress import resolve_provisioning_progress
from apps.schools.school_settings_seed import build_initial_school_settings


class OnboardingStrandHelpersTests(SimpleTestCase):
    def test_aliases_map_to_setup_studio_tracks(self):
        self.assertEqual(canonicalize_strand_code("W32_TVET"), "vocational_trade")
        self.assertEqual(canonicalize_strand_code("w31_general_k12"), "local_k12")
        self.assertEqual(canonicalize_strand_code("ib_diploma"), "ib_diploma")
        self.assertEqual(canonicalize_strand_code("not-a-strand"), "")

    def test_parse_drops_unknown_and_dedupes(self):
        self.assertEqual(
            parse_operational_strands(
                ["local_k12", "W32_TVET", "bogus", "vocational_trade"]
            ),
            ["local_k12", "vocational_trade"],
        )

    def test_prefix_normalizes_and_rejects_short(self):
        self.assertEqual(normalize_code_prefix("cm-edu!!"), "CMEDU")
        self.assertEqual(normalize_code_prefix("x"), "")
        self.assertEqual(normalize_code_prefix("toolongprefixvalue"), "TOOLONGP")

    def test_tvet_and_send_recommendation_modules(self):
        from apps.schools.onboarding_recommendations import (
            build_onboarding_recommendations,
        )

        rec = build_onboarding_recommendations(
            country_code="CM",
            education_cycles=["secondary"],
            institution_profile={
                "operational_strands": ["W32_TVET", "send"],
            },
        )["recommendations"]
        self.assertIn("vocational-pathways", rec["modules"])
        self.assertIn("special-education-support", rec["modules"])


class SchoolSettingsSeedStrandTests(SimpleTestCase):
    def test_localization_carries_strands_and_prefix(self):
        settings = build_initial_school_settings(
            country_code="CM",
            school_type_code="lycee-2nd-cycle",
            language_code="en",
            education_cycles=["lycee-2nd-cycle"],
            operational_strands=["local_k12", "vocational_trade"],
            curriculum_tracks=["local_k12", "vocational_trade"],
            code_prefix="CMEDU",
        )
        loc = settings["localization"]
        self.assertEqual(loc["operational_strands"], ["local_k12", "vocational_trade"])
        self.assertEqual(loc["code_prefix"], "CMEDU")
        self.assertIn("vocational_trade", loc["curriculum_tracks"])

    def test_seed_normalizes_dirty_prefix_and_drops_unknown_strands(self):
        settings = build_initial_school_settings(
            country_code="CM",
            operational_strands=["W32_TVET", "not-a-strand"],
            code_prefix="cm-edu!!",
        )
        loc = settings["localization"]
        self.assertEqual(loc["operational_strands"], ["vocational_trade"])
        self.assertEqual(loc["code_prefix"], "CMEDU")
        self.assertIn("vocational_trade", loc["curriculum_tracks"])


# ROOT_URLCONF makes reverse() produce the public-host path; the HOST is what makes
# the REQUEST arrive there. UrlConfSwitcherMiddleware reads the Host header, so a
# hostless request here would be served by config.urls -- the developer urlconf.
_PUBLIC = dict(
    RATELIMIT_ENABLE=False,
    ROOT_URLCONF="config.public_urls",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    **HOST_ROUTED_SETTINGS,
)


@override_settings(**_PUBLIC)
class SignupOperationalStrandCaptureTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = public_client()

    def test_signup_persists_strands_prefix_and_rejects_unknown(self):
        resp = self.client.post(
            reverse("signup_school"),
            {
                "name": "Hybrid Lycée",
                "slug": "hybrid-lycee-cm",
                "email": "owner@hybrid.test",
                "country_code": "CM",
                "school_type": ["secondary"],
                "language_codes": ["en"],
                "primary_language_code": "en",
                "operational_strands": [
                    "local_k12",
                    "W32_TVET",
                    "not-real",
                ],
                "code_prefix": "cm-ed",
                "curriculum_board": "ib",
            },
        )
        self.assertEqual(resp.status_code, 200)
        school = School.objects.get(slug="hybrid-lycee-cm")
        loc = school.settings["localization"]
        intent = school.settings["onboarding_intent"]
        self.assertEqual(loc["operational_strands"], ["local_k12", "vocational_trade"])
        self.assertEqual(loc["code_prefix"], "CMED")
        self.assertEqual(intent["code_prefix"], "CMED")
        self.assertIn("ib_diploma", loc["curriculum_tracks"])
        self.assertIn("vocational_trade", loc["curriculum_tracks"])
        modules = school.settings["recommendation_manifest"]["recommendations"]["modules"]
        self.assertIn("vocational-pathways", modules)
        self.assertIn("international-curriculum", modules)

    def test_setup_page_renders_strand_and_prefix_fields(self):
        resp = self.client.get(reverse("signup_school"), {"country_code": "CM"})
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn('name="operational_strands"', html)
        self.assertIn('data-rmc-signup-code-prefix', html)
        self.assertIn("vocational_trade", html)
        self.assertIn("special_education", html)


class StructurePrefixAndStrandTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Prefix Strand School",
            slug="prefix-strand-school",
            subdomain="prefix-strand-school",
            country_code="CM",
            is_active=True,
            settings={
                "localization": {
                    "operational_strands": ["local_k12", "vocational_trade"],
                    "code_prefix": "CMED",
                    "education_cycles": ["lycee-2nd-cycle"],
                }
            },
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )

    def test_blank_prefix_preserves_legacy_department_code(self):
        plain = School.objects.create(
            name="Plain Codes",
            slug="plain-codes-school",
            subdomain="plain-codes-school",
            country_code="CM",
            is_active=True,
        )
        dept = ensure_general_department(plain)
        self.assertTrue(dept.code.startswith("GEN-"))
        self.assertNotIn("CMED", dept.code)

    def test_prefix_applied_to_department_and_tvets_specialty(self):
        inputs = resolve_provision_seed_inputs(self.school)
        self.assertEqual(inputs.code_prefix, "CMED")
        self.assertIn("vocational_trade", inputs.strands)
        dept = ensure_general_department(self.school)
        self.assertTrue(dept.code.startswith("CMED-"))
        payload = ensure_strand_specialties(self.school)
        self.assertGreaterEqual(payload["created"], 1)
        self.assertTrue(
            Specialty.objects.filter(
                school=self.school, name="Technical / Vocational (TVET)"
            ).exists()
        )
        self.assertTrue(
            any(
                code.startswith("CMED-")
                for code in Specialty.objects.filter(school=self.school).values_list(
                    "code", flat=True
                )
            )
        )

    def test_provision_structure_is_idempotent_with_prefix(self):
        first = provision_academic_structure_for_school(
            self.school,
            school_type_codes=["lycee-2nd-cycle"],
            academic_year=self.year,
        )
        second = provision_academic_structure_for_school(
            self.school,
            school_type_codes=["lycee-2nd-cycle"],
            academic_year=self.year,
        )
        self.assertEqual(second["created_nodes"], 0)
        self.assertEqual(Department.objects.filter(school=self.school).count(), 1)
        self.assertGreaterEqual(first["strand_specialties"]["created"], 1)
        rooms = list(
            Classroom.objects.filter(school=self.school).values_list("code", flat=True)
        )
        self.assertTrue(rooms)
        self.assertTrue(any("cmed" in code.lower() for code in rooms))

    def test_send_specialty_seeded_for_special_education_strand(self):
        self.school.settings = {
            "localization": {
                "operational_strands": ["local_k12", "special_education"],
                "code_prefix": "CMED",
            }
        }
        self.school.save(update_fields=["settings"])
        payload = ensure_strand_specialties(self.school)
        self.assertGreaterEqual(payload["created"], 1)
        self.assertTrue(
            Specialty.objects.filter(
                school=self.school, name="Special Education"
            ).exists()
        )

    def test_namespaced_code_includes_prefix(self):
        code = namespaced_structure_code(self.school, "GEN")
        self.assertTrue(code.startswith("CMED-GEN-"))


class ProvisioningProgressLogIsolationTests(TestCase):
    def test_recent_log_is_school_scoped_and_chronological(self):
        a = School.objects.create(
            name="Log School A",
            slug="log-school-a",
            subdomain="log-school-a",
            country_code="CM",
            # Inactive + no phase_b marker so portal_ready is false and the
            # log is still in-flight (active SQLite schools look "succeeded").
            is_active=False,
        )
        b = School.objects.create(
            name="Log School B",
            slug="log-school-b",
            subdomain="log-school-b",
            country_code="NG",
            is_active=True,
        )
        SchoolProvisioningEvent.log_event(
            school=a,
            event_type=SchoolProvisioningEvent.EventType.STARTED,
            status=SchoolProvisioningEvent.Status.INFO,
            message="Schema migrate started",
        )
        SchoolProvisioningEvent.log_event(
            school=a,
            event_type=SchoolProvisioningEvent.EventType.ACADEMIC_STRUCTURE_READY,
            status=SchoolProvisioningEvent.Status.SUCCESS,
            message="Courses seeded",
        )
        SchoolProvisioningEvent.log_event(
            school=b,
            event_type=SchoolProvisioningEvent.EventType.FAILED,
            status=SchoolProvisioningEvent.Status.ERROR,
            message="Other tenant secret",
        )
        payload = resolve_provisioning_progress(a)
        frames = payload["recent_log"]
        messages = [frame["message"] for frame in frames]
        self.assertIn("Schema migrate started", messages)
        self.assertIn("Courses seeded", messages)
        self.assertNotIn("Other tenant secret", messages)
        self.assertLessEqual(
            frames[0]["at"] or "",
            frames[-1]["at"] or "",
        )
        self.assertIn("log_complete", payload)
        self.assertFalse(payload["log_complete"])

    def test_log_complete_when_portal_ready(self):
        school = School.objects.create(
            name="Ready Log School",
            slug="ready-log-school",
            subdomain="ready-log-school",
            country_code="CM",
            is_active=True,
            settings={"provisioning": {"phase_b_complete": True}},
        )
        payload = resolve_provisioning_progress(school)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["log_complete"])


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class PendingProvisionProgressLogApiTests(TestCase):
    def test_public_progress_api_returns_school_scoped_log_frames(self):
        from django.test import RequestFactory

        from apps.schools.views_pending_provision import (
            api_public_pending_provision_progress,
        )

        a = School.objects.create(
            name="Pending Log A",
            slug="pending-log-a",
            subdomain="pending-log-a",
            country_code="CM",
            is_active=False,
        )
        b = School.objects.create(
            name="Pending Log B",
            slug="pending-log-b",
            subdomain="pending-log-b",
            country_code="NG",
            is_active=False,
        )
        SchoolProvisioningEvent.log_event(
            school=a,
            event_type=SchoolProvisioningEvent.EventType.STARTED,
            status=SchoolProvisioningEvent.Status.INFO,
            message="Schema migrate started",
        )
        SchoolProvisioningEvent.log_event(
            school=b,
            event_type=SchoolProvisioningEvent.EventType.FAILED,
            status=SchoolProvisioningEvent.Status.ERROR,
            message="Other tenant secret",
        )
        request = RequestFactory().get(
            "/api/pending-provision/progress/",
            HTTP_HOST="pending-log-a.runmycampus.com",
        )
        response = api_public_pending_provision_progress(request)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload.get("ok"))
        self.assertIn("recent_log", payload)
        messages = [frame["message"] for frame in payload["recent_log"]]
        self.assertIn("Schema migrate started", messages)
        self.assertNotIn("Other tenant secret", messages)


@override_settings(**_PUBLIC)
class SignupDecisionsStrandPreviewTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = public_client()

    def test_decisions_preview_echoes_canonical_strands_and_drops_unknown(self):
        resp = self.client.get(
            reverse("signup_decisions_preview"),
            {
                "country_code": "CM",
                "cycles": "secondary",
                "strands": "local_k12,W32_TVET,not-real",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(
            body.get("operational_strands"),
            ["local_k12", "vocational_trade"],
        )
        self.assertTrue(body.get("dimensions"))


class CurriculumTrackApplyTests(TestCase):
    def test_provision_inputs_apply_tracks_to_grading_blob(self):
        from apps.evals.grading_wizard_kernel import apply_curriculum_tracks

        school = School.objects.create(
            name="Track Apply School",
            slug="track-apply-school",
            subdomain="track-apply-school",
            country_code="CM",
            is_active=True,
            settings={
                "localization": {
                    "operational_strands": ["local_k12", "vocational_trade"],
                    "curriculum_tracks": ["local_k12", "vocational_trade"],
                }
            },
        )
        inputs = resolve_provision_seed_inputs(school)
        result = apply_curriculum_tracks(
            school=school, payload={"tracks": list(inputs.curriculum_tracks)}
        )
        school.refresh_from_db()
        self.assertTrue(result["ok"])
        self.assertIn("vocational_trade", result["curriculum_tracks"])
        self.assertEqual(
            school.settings["grading"]["curriculum_tracks"],
            ["local_k12", "vocational_trade"],
        )
