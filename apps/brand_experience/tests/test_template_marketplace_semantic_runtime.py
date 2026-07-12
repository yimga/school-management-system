"""Semantic runtime tests for the ExperienceTemplate marketplace program.

These tests close the structural-vs-semantic gap called out in the
plan-compliance verifier: the registry / file / route checks prove that
the artifacts exist; THIS module proves the actual code paths execute
correctly under a Django request cycle and that the Studio OS Experience
fold receives real overlay context from the live view.

Honest scope: this module covers Studio OS Experience mode, tenant marketplace
views, Setup Studio, and TemplateAuditEvent append-only behavior. It does not
exercise the 6 operator ``/configuration/experience-templates/*`` routes; those
reuse the platform_runtime pack lifecycle views with their own coverage.

Wave: post-batch-1401 semantic-runtime closeout (2026-05-23).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.http import Http404
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import set_urlconf

from apps.brand_experience import experience_templates as et
from apps.brand_experience import views_template_marketplace as views_tm
from apps.brand_experience.experience_templates import (
    LAYOUT_FAMILY_NAMES,
    list_overlays,
)
from apps.brand_experience.models_template import (
    TemplateAuditEventReadOnlyError,
    hash_tenant_slug,
    record_template_event,
)
from apps.policies.models import BlueprintPack
from apps.registries.models import (
    CalendarSystemRegistry,
    CountryRegistry,
    CurrencyRegistry,
    EducationSystemTypeRegistry,
    GradeScaleRegistry,
    InstitutionTypeRegistry,
    LocaleRegistry,
    SubdivisionRegistry,
    TimeZoneRegistry,
)
from apps.schools.models import School
from apps.setup_studio.services import get_setup_studio_payload
from apps.siteconfig.models_platform_catalog import RegionConfig
from apps.studio_os.views import studio_shell

User = get_user_model()


def _bootstrap_tenant_school(*, slug: str) -> School:
    """Create a minimal tenant school + supporting registry rows.

    Mirrors the bootstrap in ``apps/setup_studio/tests/test_setup_studio_services.py``
    so that Setup Studio / Studio OS / template marketplace views can run end-to-end
    under the test request cycle.
    """
    region, _ = RegionConfig.objects.get_or_create(
        code="TST",
        defaults={
            "name": "Test Region",
            "default_currency": "XAF",
            "grading_scale": "0-20",
        },
    )
    school = School.objects.create(
        name=f"Runtime School {slug}",
        slug=slug,
        subdomain=slug,
        country_code="CM",
        timezone="UTC",
        default_region=region,
        school_type="BASE_SCHOOL",
        is_active=True,
    )
    cm, _ = CountryRegistry.objects.get_or_create(
        code="CM",
        defaults={"name": "Cameroon", "is_active": True},
    )
    sub, _ = SubdivisionRegistry.objects.get_or_create(
        country=cm, code="LT",
        defaults={"name": "Littoral", "is_active": True},
    )
    school.subdivision = sub
    school.save(update_fields=["subdivision"])
    TimeZoneRegistry.objects.get_or_create(
        code="UTC",
        defaults={"name": "Coordinated Universal Time", "is_active": True},
    )
    CurrencyRegistry.objects.get_or_create(
        code="XAF",
        defaults={"name": "CFA Franc BEAC", "is_active": True},
    )
    LocaleRegistry.objects.get_or_create(
        code="en",
        defaults={"name": "English", "is_active": True},
    )
    CalendarSystemRegistry.objects.get_or_create(
        code="gregorian",
        defaults={"name": "Gregorian (civil)", "is_active": True},
    )
    InstitutionTypeRegistry.objects.get_or_create(
        code="BASE_SCHOOL",
        defaults={"name": "Base school", "is_active": True},
    )
    GradeScaleRegistry.objects.get_or_create(
        code="0-20",
        defaults={"name": "0-20 scale", "is_active": True},
    )
    EducationSystemTypeRegistry.objects.get_or_create(
        code="EN",
        defaults={"name": "English sub-system", "is_active": True},
    )
    BlueprintPack.objects.get_or_create(
        slug="cm-launch",
        defaults={
            "name": "Cameroon launch baseline",
            "description": "Regional baseline for Cameroon schools.",
            "supported_country_scope": ["CM"],
            "default_dashboard_pack_id": 1,
            "default_workflow_pack_id": 1,
            "is_active": True,
        },
    )
    return school


def _attach_tenant(request, *, user, school):
    """Mimic tenant middleware: attach user + tenant resolution + force tenant URL graph.

    Sets the thread-local URL conf so ``{% url 'template_marketplace:...' %}`` resolves
    inside templates (RequestFactory does not run middleware, so ``request.urlconf``
    alone is not enough for the template layer's ``reverse()``).
    """
    request.user = user
    request.school = school
    request.tenant = school
    request.urlconf = "config.tenant_urls"
    set_urlconf("config.tenant_urls")
    return request


class ExperienceFoldPartialContractTests(SimpleTestCase):
    """The fold partial honors its context contract end-to-end.

    Renders the partial directly via Django's template engine with the exact
    context shape the Studio OS view produces; proves the partial works whenever
    the view delivers what the contract promises.
    """

    def _build_context(self):
        overlays = list_overlays(tenant_safe_only=True)[:3]
        for row in overlays:
            row["layout_family_name"] = LAYOUT_FAMILY_NAMES.get(
                row.get("layout_family"), ""
            )
            row["detail_url"] = "/school/studio/templates/" + row["key"] + "/"
        return {
            "experience_template_overlays": overlays,
            "experience_template_marketplace_urls": {
                "browse": "/school/studio/templates/",
                "ai_recommend": "/school/studio/templates/recommend/",
            },
        }, overlays

    def test_fold_renders_marker_with_overlay_rows(self):
        context, overlays = self._build_context()
        body = render_to_string(
            "studio_os/partials/experience_templates_fold.html",
            context=context,
        )
        self.assertIn(
            'data-page-marker="rmc-studio-experience-templates-fold"', body
        )
        # Every overlay key + its detail URL is rendered as a list item
        for row in overlays:
            self.assertIn(row["key"], body)
            self.assertIn(row["detail_url"], body)
        # Browse + ai-recommend CTAs honored
        self.assertIn("/school/studio/templates/", body)
        self.assertIn("/school/studio/templates/recommend/", body)

    def test_fold_renders_nothing_when_browse_url_absent(self):
        body = render_to_string(
            "studio_os/partials/experience_templates_fold.html",
            context={
                "experience_template_overlays": [],
                "experience_template_marketplace_urls": {},
            },
        )
        self.assertNotIn("rmc-studio-experience-templates-fold", body)

    def test_fold_empty_state_when_overlays_empty_but_urls_present(self):
        body = render_to_string(
            "studio_os/partials/experience_templates_fold.html",
            context={
                "experience_template_overlays": [],
                "experience_template_marketplace_urls": {
                    "browse": "/school/studio/templates/",
                    "ai_recommend": "/school/studio/templates/recommend/",
                },
            },
        )
        self.assertIn(
            'data-page-marker="rmc-studio-experience-templates-fold"', body
        )
        self.assertIn("rmc-studio-experience-templates-fold__empty", body)


class StudioOSExperienceModeViewRuntimeTests(TestCase):
    """The Studio OS Experience-mode view injects overlay context the partial expects."""

    def setUp(self):
        self.school = _bootstrap_tenant_school(slug="semantic-runtime-studio")
        self.user = User.objects.create_superuser(
            username="rt-staff",
            email="rt-staff@example.com",
            password="x",
        )
        self.user.is_staff = True
        self.user.save(update_fields=["is_staff"])
        self.rf = RequestFactory()

    def tearDown(self):
        set_urlconf(None)

    def _build_request(self):
        request = self.rf.get("/studio/experience/")
        # studio_os.services.get_studio_activity_feed reads request.session — RequestFactory
        # doesn't attach one, so we supply an in-memory session manually.
        from django.contrib.sessions.backends.signed_cookies import (
            SessionStore as SignedCookiesSessionStore,
        )
        request.session = SignedCookiesSessionStore()
        return _attach_tenant(request, user=self.user, school=self.school)

    def test_experience_mode_view_renders_fold_with_overlays(self):
        request = self._build_request()
        response = studio_shell(request, mode="experience")
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn(
            'data-page-marker="rmc-studio-experience-templates-fold"', body
        )
        first_tenant_safe_key = next(
            o["key"] for o in list_overlays(tenant_safe_only=True)
        )
        self.assertIn(first_tenant_safe_key, body)
        self.assertIn("/school/studio/templates/", body)


class SetupStudioExperienceTemplateStepRuntimeTests(TestCase):
    """The select_experience_template step actually surfaces in the live Setup Studio payload."""

    def setUp(self):
        self.school = _bootstrap_tenant_school(slug="semantic-runtime-setup")

    def test_select_experience_template_step_present(self):
        payload = get_setup_studio_payload(self.school)
        step_keys = {s["key"] for s in payload["steps"]}
        self.assertIn("select_experience_template", step_keys)


class TenantTemplateMarketplaceViewsRuntimeTests(TestCase):
    """All 9 tenant template marketplace views render under a real request cycle."""

    def setUp(self):
        self.school = _bootstrap_tenant_school(slug="semantic-runtime-tenant")
        self.user = User.objects.create_user(
            username="rt-tenant",
            email="rt-tenant@example.com",
            password="x",
        )
        self.rf = RequestFactory()
        self.tenant_safe_key = next(
            o.key for o in et.OVERLAYS if not o.is_operator_only()
        )
        self.operator_only_key = next(
            o.key for o in et.OVERLAYS if o.is_operator_only()
        )

    def tearDown(self):
        set_urlconf(None)

    def _req(self, path: str = "/school/studio/templates/"):
        request = self.rf.get(path)
        # portal_base context processors (get_effective_portal_role) read
        # request.session — RequestFactory doesn't attach one, so supply an
        # in-memory session (mirrors _build_request above).
        from django.contrib.sessions.backends.signed_cookies import (
            SessionStore as SignedCookiesSessionStore,
        )
        request.session = SignedCookiesSessionStore()
        return _attach_tenant(request, user=self.user, school=self.school)

    def test_browse_view_returns_200(self):
        response = views_tm.tenant_template_marketplace(self._req())
        self.assertEqual(response.status_code, 200)

    def test_detail_view_returns_200_for_tenant_safe_key(self):
        response = views_tm.tenant_template_detail(self._req(), key=self.tenant_safe_key)
        self.assertEqual(response.status_code, 200)

    def test_detail_view_404s_for_operator_only_key(self):
        with self.assertRaises(Http404):
            views_tm.tenant_template_detail(self._req(), key=self.operator_only_key)

    def test_preview_view_returns_200(self):
        response = views_tm.tenant_template_preview(self._req(), key=self.tenant_safe_key)
        self.assertEqual(response.status_code, 200)

    def test_compare_view_returns_200(self):
        response = views_tm.tenant_template_compare(self._req(), key=self.tenant_safe_key)
        self.assertEqual(response.status_code, 200)

    def test_apply_view_get_returns_200(self):
        response = views_tm.tenant_template_apply(self._req(), key=self.tenant_safe_key)
        self.assertEqual(response.status_code, 200)

    def test_local_first_catalog_returns_200(self):
        response = views_tm.tenant_local_first_catalog(self._req(), country_code="CM")
        self.assertEqual(response.status_code, 200)

    def test_ai_recommendation_returns_json(self):
        response = views_tm.tenant_template_ai_recommendation(self._req())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("application/json"))

    def test_rollback_view_get_returns_200(self):
        response = views_tm.tenant_template_rollback(self._req(), key=self.tenant_safe_key)
        self.assertEqual(response.status_code, 200)

    def test_customize_view_get_returns_200(self):
        response = views_tm.tenant_template_customize(self._req(), key=self.tenant_safe_key)
        self.assertEqual(response.status_code, 200)


class TemplateAuditEventAppendOnlyRuntimeTests(TestCase):
    """TemplateAuditEvent append-only contract holds under the live ORM."""

    def test_record_creates_audit_row_with_hashed_tenant(self):
        event = record_template_event(
            tenant_slug="some-tenant",
            event_type="template.preview",
            template_key="t-test-key",
        )
        self.assertEqual(event.tenant_id_hash, hash_tenant_slug("some-tenant"))
        self.assertEqual(event.event_type, "template.preview")
        self.assertEqual(event.template_key, "t-test-key")

    def test_record_strips_sensitive_payload_keys(self):
        event = record_template_event(
            tenant_slug="some-tenant",
            event_type="template.preview",
            template_key="t-test-key",
            payload={"safe_key": "ok", "password": "shh", "token": "shh"},
        )
        self.assertIn("safe_key", event.payload_summary)
        self.assertNotIn("password", event.payload_summary)
        self.assertNotIn("token", event.payload_summary)

    def test_audit_event_save_after_create_raises_readonly(self):
        event = record_template_event(
            tenant_slug="some-tenant",
            event_type="template.preview",
            template_key="t-test-key",
        )
        event.event_type = "template.applied"
        with self.assertRaises(TemplateAuditEventReadOnlyError):
            event.save()
