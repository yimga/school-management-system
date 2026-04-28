"""North Star SLICE 3 — curriculum template registry and operator page."""

import uuid

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.siteconfig.curriculum_templates_service import (
    curriculum_template_keys,
    get_curriculum_template,
    get_template_subject_seed,
    get_template_term_labels,
    get_template_terminology,
    iter_curriculum_templates,
    reload_curriculum_templates_cache,
)
from apps.siteconfig.models import Plan
from apps.siteconfig.models_platform_catalog import RegionConfig
from apps.schools.models import School

_REQUIRED_KEYS = frozenset(
    {
        "british_igcse",
        "american_k12",
        "waec_wassce",
        "francophone_bac",
        "cameroon_anglophone_gce",
    }
)

_T_HOST = "ct3ns.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class CurriculumTemplatesSlice3Tests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(
            name="Slice3",
            slug="slice-3-plan",
            included_features=["core"],
            is_active=True,
        )
        cls.region = RegionConfig.objects.create(
            code="C3",
            name="Slice3land",
            timezone="UTC",
            default_currency="USD",
        )
        cls.school = School.objects.create(
            name="Curriculum Template School",
            slug="ct3ns",
            subdomain="ct3ns",
            is_active=True,
            plan=cls.plan,
            default_region=cls.region,
        )

    def setUp(self):
        reload_curriculum_templates_cache()

    def test_required_template_keys_exist(self):
        keys = set(curriculum_template_keys())
        self.assertTrue(_REQUIRED_KEYS.issubset(keys), msg=keys)

    def test_each_template_has_required_fields(self):
        for key in _REQUIRED_KEYS:
            t = get_curriculum_template(key)
            self.assertIsNotNone(t, msg=key)
            assert t is not None
            self.assertIn("grading_scale_key", t)
            self.assertTrue(t.get("grading_scale_key"))
            self.assertIn("term_labels", t)
            self.assertIsInstance(t.get("term_labels"), list)
            self.assertGreater(len(t.get("term_labels") or []), 0)
            self.assertIn("terminology_map", t)
            self.assertIsInstance(t.get("terminology_map"), dict)
            self.assertGreater(len(t.get("terminology_map") or {}), 0)
            self.assertIn("report_template_family", t)
            self.assertTrue(t.get("report_template_family"))

    def test_service_helpers(self):
        tm = get_template_terminology("british_igcse")
        self.assertIsInstance(tm, dict)
        self.assertIn("grade", tm)
        lbls = get_template_term_labels("american_k12")
        self.assertTrue(len(lbls) >= 2)
        seed = get_template_subject_seed("waec_wassce")
        self.assertTrue(all(isinstance(x, dict) and "name" in x for x in seed))
        seen = {x["template_key"] for x in iter_curriculum_templates()}
        self.assertTrue(_REQUIRED_KEYS.issubset(seen))

    def test_operator_page_renders_for_admin(self):
        u = User.objects.create_user(
            username=f"adm_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.force_login(u)
        url = reverse("siteconfig:curriculum_templates", urlconf="config.tenant_urls")
        resp = c.get(url)
        self.assertEqual(resp.status_code, 200, msg=resp.content[:800])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-cp-evidence-surface="curriculum-templates"', body)
        self.assertIn('data-rmc-curriculum-templates="1"', body)

    def test_page_lists_all_named_templates(self):
        u = User.objects.create_user(
            username=f"adm2_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.force_login(u)
        url = reverse("siteconfig:curriculum_templates", urlconf="config.tenant_urls")
        body = c.get(url).content.decode("utf-8", errors="replace")
        for label in (
            "British / IGCSE",
            "American K–12",
            "WAEC / WASSCE",
            "Francophone / Baccalauréat",
            "Cameroon Anglophone / GCE",
        ):
            self.assertIn(label, body)

    def test_related_links_present(self):
        u = User.objects.create_user(
            username=f"adm3_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.force_login(u)
        url = reverse("siteconfig:curriculum_templates", urlconf="config.tenant_urls")
        body = c.get(url).content.decode("utf-8", errors="replace")
        self.assertIn("/siteconfig/grading-scales/bands/", body)
        self.assertIn("/siteconfig/grading-scales/region-scales/", body)
        self.assertIn("/siteconfig/configuration/runtime/", body)
        self.assertIn("/siteconfig/console/", body)
        self.assertIn("/siteconfig/grading-settings/", body)

    def test_teacher_forbidden(self):
        tu = User.objects.create_user(
            username=f"t_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.TEACHER,
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.force_login(tu)
        url = reverse("siteconfig:curriculum_templates", urlconf="config.tenant_urls")
        resp = c.get(url)
        self.assertEqual(resp.status_code, 403)

    def test_preview_only_copy(self):
        u = User.objects.create_user(
            username=f"adm4_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.force_login(u)
        url = reverse("siteconfig:curriculum_templates", urlconf="config.tenant_urls")
        body = c.get(url).content.decode("utf-8", errors="replace")
        self.assertIn("Preview only.", body)
        self.assertIn("Applying templates requires a future guided setup flow.", body)
        self.assertIn('data-rmc-curriculum-preview-notice="1"', body)

    def test_no_fake_apply_control(self):
        u = User.objects.create_user(
            username=f"adm5_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.force_login(u)
        url = reverse("siteconfig:curriculum_templates", urlconf="config.tenant_urls")
        body = c.get(url).content.decode("utf-8", errors="replace")
        lower = body.lower()
        self.assertNotIn("apply template", lower)
        self.assertNotIn('name="apply_curriculum"', body)
        self.assertNotIn("curriculum_templates_apply", body)

    def test_curriculum_templates_url_resolves(self):
        url = reverse("siteconfig:curriculum_templates")
        self.assertIn("/siteconfig/curriculum/templates/", url)

    def test_effective_terminology_block_always_shown(self):
        u = User.objects.create_user(
            username=f"adm6_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        c = Client(HTTP_HOST=_T_HOST)
        c.force_login(u)
        url = reverse("siteconfig:curriculum_templates", urlconf="config.tenant_urls")
        body = c.get(url).content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-terminology-engine="1"', body)
        self.assertIn("product defaults", body)

    def test_francophone_curriculum_template_shows_terminology_highlight(self):
        prior = dict(self.school.settings or {})
        try:
            st = dict(prior)
            st["curriculum_template_key"] = "francophone_bac"
            self.school.settings = st
            self.school.save(update_fields=["settings"])
            u = User.objects.create_user(
                username=f"adm7_{uuid.uuid4().hex[:8]}",
                password="x" * 8,
                role=User.Role.ADMIN,
                is_staff=True,
            )
            c = Client(HTTP_HOST=_T_HOST)
            c.force_login(u)
            url = reverse("siteconfig:curriculum_templates", urlconf="config.tenant_urls")
            body = c.get(url).content.decode("utf-8", errors="replace")
            self.assertIn('data-rmc-terminology-highlight="francophone-pattern"', body)
            self.assertIn("Note", body)
            self.assertIn("Trimestre", body)
        finally:
            self.school.settings = prior
            self.school.save(update_fields=["settings"])
