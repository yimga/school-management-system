import io
import json

from django.core.management import call_command
from django.template import Context, Template
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.platform_runtime.administration_catalog import (
    TENANT_CONFIGURATION_SECTIONS,
    _resolve_tenant_configuration_route,
)
from apps.schools.models import School
from apps.schools.runtime_assignment_evidence import runtime_assignment_evidence
from apps.schools.setup_health import setup_health_score
from apps.siteconfig.models_dashboard import (
    DashboardPack,
    DashboardPackAssignment,
    DashboardTemplate,
    TenantLayoutAssignment,
)
from apps.siteconfig.portal_sidebar_items import build_portal_sidebar_groups


class TenantConfigurationRouteContractTests(SimpleTestCase):
    def test_every_configuration_action_reverses_in_tenant_urlconf(self):
        routes = []
        for section in TENANT_CONFIGURATION_SECTIONS:
            route, error = _resolve_tenant_configuration_route(
                section, urlconf="config.tenant_urls"
            )
            self.assertFalse(error, section["name"])
            self.assertTrue(route.startswith("/"), section["name"])
            self.assertNotIn("/super/", route)
            routes.append(route)
        self.assertEqual(len(routes), 14)

    def test_canonical_and_legacy_routes_have_named_owners(self):
        self.assertEqual(reverse("academics:hub", urlconf="config.tenant_urls"), "/academics/")
        self.assertEqual(
            reverse("portal:offline_sync_legacy", urlconf="config.tenant_urls"),
            "/portal/offline-sync/",
        )
        self.assertEqual(reverse("compliance:home", urlconf="config.tenant_urls"), "/compliance/")


class SharedStructuredComponentTests(SimpleTestCase):
    def test_metric_ticker_preserves_mappings_and_rejects_string(self):
        source = '{% load rmc_component_tags %}{% for metric in metrics|valid_metric_items:8 %}{{ metric.label }}|{% endfor %}'
        rendered = Template(source).render(Context({"metrics": [{"label": "Fees"}, {"label": "Aging"}]}))
        self.assertEqual(rendered, "Fees|Aging|")
        self.assertEqual(Template(source).render(Context({"metrics": "not-a-list"})), "")

    def test_metric_ticker_caps_at_eight(self):
        source = '{% load rmc_component_tags %}{{ metrics|valid_metric_items:8|length }}'
        rendered = Template(source).render(Context({"metrics": [{"label": str(i)} for i in range(20)]}))
        self.assertEqual(rendered, "8")

    def test_sidebar_groups_accumulate_interleaved_sections_once(self):
        groups = build_portal_sidebar_groups(
            [
                {"id": "home", "section": "Home"},
                {"id": "profile", "section": "Account"},
                {"id": "dashboard", "section": "Home", "is_current": True},
            ]
        )
        self.assertEqual([group["name"] for group in groups], ["Home", "Account"])
        self.assertEqual([item["id"] for item in groups[0]["items"]], ["home", "dashboard"])
        self.assertTrue(groups[0]["is_active"])


class RuntimeAssignmentEvidenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(name="Runtime Evidence", slug="runtime-evidence", subdomain="runtime-evidence", is_active=True)
        cls.pack = DashboardPack.objects.create(code="runtime-admin", name="Runtime admin", is_active=True)
        cls.template = DashboardTemplate.objects.create(name="Runtime template", dashboard_pack=cls.pack, is_active=True)

    def test_active_layout_counts_when_legacy_slugs_are_empty(self):
        TenantLayoutAssignment.objects.create(school=self.school, role="ADMIN", template=self.template, is_active=True)
        evidence = runtime_assignment_evidence(self.school)
        self.assertTrue(evidence["passed"])
        self.assertEqual(evidence["source"], "tenant_layout")
        self.assertEqual(setup_health_score(self.school)["runtime_evidence"]["source"], "tenant_layout")

    def test_active_pack_counts_and_inactive_assignment_does_not(self):
        assignment = DashboardPackAssignment.objects.create(
            school=self.school, role="admin", dashboard_pack=self.pack, is_active=False
        )
        self.assertFalse(runtime_assignment_evidence(self.school)["passed"])
        assignment.is_active = True
        assignment.save(update_fields=["is_active"])
        self.assertEqual(runtime_assignment_evidence(self.school)["source"], "dashboard_pack")

    def test_other_school_assignment_never_counts(self):
        other = School.objects.create(name="Other Runtime", slug="other-runtime", subdomain="other-runtime", is_active=True)
        TenantLayoutAssignment.objects.create(school=other, role="ADMIN", template=self.template, is_active=True)
        self.assertFalse(runtime_assignment_evidence(self.school)["passed"])

    def test_legacy_fallback_is_explicit(self):
        self.school.default_dashboard_slug = "legacy-admin"
        evidence = runtime_assignment_evidence(self.school)
        self.assertTrue(evidence["passed"])
        self.assertEqual(evidence["source"], "legacy_fallback")

    def test_reconciliation_command_is_scoped_and_dry_run_by_default(self):
        output = io.StringIO()
        call_command(
            "assign_default_dashboard_packs",
            school_slug=self.school.slug,
            dry_run=True,
            json=True,
            stdout=output,
        )
        payload = json.loads(output.getvalue().strip().splitlines()[-1])
        self.assertFalse(payload["applied"])
        self.assertEqual(payload["matched"], 1)
        self.assertEqual(payload["schools"][0]["school"], str(self.school.pk))
