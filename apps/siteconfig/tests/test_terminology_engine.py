"""North Star SLICE 4 — tenant terminology service + template tags."""

import uuid

from django.template import Context, Engine
from django.test import RequestFactory, TestCase, override_settings

from apps.siteconfig.curriculum_templates_service import reload_curriculum_templates_cache
from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig
from apps.siteconfig.terminology_service import (
    DEFAULT_TERMINOLOGY,
    describe_terminology_resolution,
    get_effective_terminology_for_school,
    get_grade_label,
    get_gpa_label,
    get_term_label,
)
from apps.schools.models import School

_T_HOST = "t4ns.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class TerminologyEngineSlice4Tests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="T4",
            slug="t4-plan",
            included_features=["core"],
            is_active=True,
        )
        cls.region = RegionConfig.objects.create(
            code="T4",
            name="T4land",
            timezone="UTC",
            default_currency="USD",
        )

    def setUp(self):
        reload_curriculum_templates_cache()

    def _school(self, **settings_kw):
        slug = f"t4-{uuid.uuid4().hex[:8]}"
        school = School.objects.create(
            name="Terminology School",
            slug=slug,
            subdomain=slug,
            is_active=True,
            plan=self.plan,
            default_region=self.region,
            settings={},
        )
        if settings_kw:
            base = dict(school.settings or {})
            base.update(settings_kw)
            school.settings = base
            school.save(update_fields=["settings"])
        return school

    def test_each_registry_template_maps_expected_labels(self):
        expectations = {
            "francophone_bac": {
                "grade": "Note",
                "gpa": "Moyenne",
                "term": "Trimestre",
                "report_card": "Bulletin",
            },
            "american_k12": {
                "grade": "Grade",
                "gpa": "GPA",
                "term": "Semester",
                "report_card": "Report card",
            },
        }
        for key, exp in expectations.items():
            school = self._school(curriculum_template_key=key)
            eff = get_effective_terminology_for_school(school)
            self.assertEqual(eff["grade"], exp["grade"], msg=key)
            self.assertEqual(eff["gpa"], exp["gpa"], msg=key)
            self.assertEqual(eff["term"], exp["term"], msg=key)
            self.assertEqual(eff["report_card"], exp["report_card"], msg=key)

    def test_tenant_override_precedence_over_template(self):
        school = self._school(
            curriculum_template_key="francophone_bac",
            terminology={"term": "OverridePeriod", "grade": "XNote"},
        )
        self.assertEqual(get_term_label(school), "OverridePeriod")
        self.assertEqual(get_grade_label(school), "XNote")
        self.assertEqual(get_gpa_label(school), "Moyenne")
        res = describe_terminology_resolution(school)
        self.assertIn("curriculum template", res)
        self.assertIn("override", res)

    def test_defaults_without_school_and_empty_settings(self):
        self.assertEqual(
            get_effective_terminology_for_school(None), dict(DEFAULT_TERMINOLOGY)
        )
        school = self._school()
        self.assertEqual(
            get_effective_terminology_for_school(school), dict(DEFAULT_TERMINOLOGY)
        )
        self.assertEqual(describe_terminology_resolution(school), "product defaults")

    def test_template_tags_request_school(self):
        school = self._school(curriculum_template_key="francophone_bac")
        factory = RequestFactory()
        request = factory.get("/")
        request.school = school
        engine = Engine.get_default()
        tpl = engine.from_string(
            "{% load terminology_tags %}{% grade_label %}|{% term_label %}"
        )
        out = tpl.render(Context({"request": request}))
        self.assertEqual(out, "Note|Trimestre")

    def test_template_tags_no_school_falls_back_to_defaults(self):
        engine = Engine.get_default()
        tpl = engine.from_string("{% load terminology_tags %}{% grade_label %}")
        out = tpl.render(Context({}))
        self.assertEqual(out, DEFAULT_TERMINOLOGY["grade"])

    def test_template_tags_student_school(self):
        school = self._school(curriculum_template_key="waec_wassce")
        from types import SimpleNamespace

        student = SimpleNamespace(school=school)
        engine = Engine.get_default()
        tpl = engine.from_string("{% load terminology_tags %}{% report_label %}")
        out = tpl.render(Context({"student": student}))
        self.assertEqual(out, "Report card")

    def test_marks_list_template_renders_terminology(self):
        from django.contrib.auth.models import AnonymousUser
        from django.template.loader import render_to_string

        school = self._school(curriculum_template_key="american_k12")
        rf = RequestFactory()
        request = rf.get("/evals/teacher/marks/")
        request.user = AnonymousUser()
        request.school = school
        html = render_to_string(
            "teacher/marks_list.html",
            {
                "export_csv_query": "",
                "export_pdf_query": "",
                "term_choices": [],
                "classrooms": [],
                "subjects": [],
                "mark_rows": [],
                "rosetta_target": None,
                "rosetta_target_choices": [("", "—")],
                "selected": {"compare": ""},
            },
            request=request,
        )
        self.assertIn("Semester", html)
        self.assertIn("Grade", html)
