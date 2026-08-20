"""Operator UI for feature ③ — the Edge Onboarding Runbook surface.

Each test FAILS without the operator view + route + template (NoReverseMatch /
missing content). Proves: an operator can load the page and it lists schools;
selecting a school renders THAT school's runbook (a command carrying the slug);
the verification + sync-gate sections render (transport patched — no network);
and a non-operator is denied.
"""
from __future__ import annotations

import uuid

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import School
from apps.schools.rls_context import rls_bypass
from apps.sync_engine.models import EdgeSyncRun
from apps.test_utils.http_clients import login_manager_client

MANAGER_HOST = "manager.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["*"])
class EdgeOnboardingOperatorUITests(TestCase):
    SLUG = "edge-ui-school"
    PASSWORD = "testpass123"

    def setUp(self):
        self.operator = User.objects.create_user(
            username="edge_ui_operator",
            password=self.PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        self.client = login_manager_client(self.operator, password=self.PASSWORD)
        self.school = self._make_school()
        self.url = reverse("super:edge_onboarding_runbook")

    def _make_school(self, *, slug=SLUG, active=True):
        with rls_bypass():
            School.objects.filter(slug=slug).delete()
        return School.objects.create(
            id=uuid.uuid4(),
            name="Edge UI High School",
            slug=slug,
            subdomain=slug,
            is_active=active,
            is_approved=True,
            country_code="CM",
            settings={},
        )

    # (a) operator can load the page and it lists schools ----------------------
    def test_operator_loads_page_and_it_lists_schools(self):
        response = self.client.get(self.url, HTTP_HOST=MANAGER_HOST)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        # The selector lists the school and, with nothing chosen, prompts a pick.
        self.assertIn("Edge UI High School", body)
        self.assertIn("Select a school", body)
        self.assertIn('id="edge-onboarding-selector"', body)

    # (b) selecting a school renders THAT school's runbook ---------------------
    def test_selecting_school_renders_its_runbook(self):
        response = self.client.get(
            self.url, {"school": self.SLUG}, HTTP_HOST=MANAGER_HOST
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        # A generated, school-specific command line (verbatim, copy-pasteable).
        self.assertIn(f"--slug {self.SLUG}", body)
        self.assertIn(f"--school {self.SLUG}", body)
        # The runbook section rendered.
        self.assertIn('id="edge-onboarding-runbook"', body)
        self.assertIn("Provision the sovereign tenant shell", body)

    # (b') the plain-text hand-off export --------------------------------------
    def test_text_export_hands_off_the_runbook(self):
        response = self.client.get(
            self.url, {"school": self.SLUG, "format": "txt"}, HTTP_HOST=MANAGER_HOST
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response["Content-Type"].startswith("text/plain"))
        body = response.content.decode("utf-8")
        self.assertIn("Edge Onboarding Runbook", body)
        self.assertIn(f"--slug {self.SLUG}", body)
        self.assertIn("RUNBOOK", body)

    # (c) readiness preview + box-side gate note render; NO write on a GET ------
    def test_readiness_preview_and_gate_note_render_without_writing(self):
        before = EdgeSyncRun.objects.count()
        response = self.client.get(
            self.url, {"school": self.SLUG}, HTTP_HOST=MANAGER_HOST
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        # The gate is presented as a BOX-SIDE step, not fake-run on this cloud console.
        self.assertIn('id="edge-onboarding-sync-gate"', body)
        self.assertIn("Runs on the box", body)
        self.assertNotIn("Cleared for offline", body)
        # Readiness preview (all steps except the box-side gate) rendered; a bare
        # school fails several checks.
        self.assertIn('id="edge-onboarding-verification"', body)
        self.assertIn("Readiness preview", body)
        self.assertIn("FAIL", body)
        # A cloud GET must record NO EdgeSyncRun — the writing gate never runs here.
        self.assertEqual(EdgeSyncRun.objects.count(), before)
        from apps.lifecycle.models_edge_onboarding import EdgeOnboardingRun

        self.assertEqual(EdgeOnboardingRun.objects.count(), 0)

    def test_live_sync_row_on_manager_renders_as_host_observability_not_box_proof(self):
        EdgeSyncRun.objects.create(
            school=self.school, mode="live", ok=True, conflicts=0, pushed=2, pulled=3
        )
        response = self.client.get(
            self.url, {"school": self.SLUG}, HTTP_HOST=MANAGER_HOST
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("not box proof", body.lower())
        self.assertIn("conflicts", body.lower())
        self.assertEqual(EdgeSyncRun.objects.filter(mode="live").count(), 1)

    def test_runbook_names_runs_on_and_data_seed_without_fresh(self):
        response = self.client.get(
            self.url, {"school": self.SLUG}, HTTP_HOST=MANAGER_HOST
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("cloud", body)
        self.assertIn("box", body)
        self.assertIn("lan", body)
        self.assertIn("seed_operational_data", body)
        self.assertIn("import_tenant_bundle", body)
        self.assertIn("edge_onboarding_verify", body)
        self.assertNotIn("shell -c", body)
        self.assertIn("Copy command", body)
        self.assertIn("source tenant", body.lower())

    def test_text_export_includes_runs_on(self):
        response = self.client.get(
            self.url, {"school": self.SLUG, "format": "txt"}, HTTP_HOST=MANAGER_HOST
        )
        body = response.content.decode("utf-8")
        self.assertIn("runs_on=", body)
        self.assertIn("seed_operational_data", body)
        self.assertIn("Delta sync is not a bulk loader", body)

    def test_skip_migration_cloud_post_requires_12_char_reason(self):
        from apps.lifecycle.models_edge_onboarding import EdgeOnboardingRun

        short = self.client.post(
            self.url,
            {"school": self.SLUG, "lifecycle_action": "skip_migration_cloud", "skip_reason": "nope"},
            HTTP_HOST=MANAGER_HOST,
        )
        self.assertIn(short.status_code, (302, 200))
        self.assertEqual(EdgeOnboardingRun.objects.filter(kind="skip_mc").count(), 0)

        ok = self.client.post(
            self.url,
            {
                "school": self.SLUG,
                "lifecycle_action": "skip_migration_cloud",
                "skip_reason": "Empty shell — no SIS files for this campus.",
            },
            HTTP_HOST=MANAGER_HOST,
        )
        self.assertEqual(ok.status_code, 302)
        self.assertEqual(EdgeOnboardingRun.objects.filter(kind="skip_mc").count(), 1)

    # (c') a school with failures renders the failures, never 500 --------------
    def test_school_with_failures_renders_without_500(self):
        response = self.client.get(
            self.url, {"school": self.SLUG}, HTTP_HOST=MANAGER_HOST
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Readiness preview", body)
        self.assertIn("Runs on the box", body)

    # (d) a non-operator is denied --------------------------------------------
    def test_non_operator_is_denied(self):
        plain = User.objects.create_user(
            username="edge_ui_plain",
            password=self.PASSWORD,
            is_staff=False,
            is_superuser=False,
        )
        denied_client = self.client_class()
        denied_client.force_login(plain)
        response = denied_client.get(self.url, {"school": self.SLUG})
        # Bounced (login/redirect) or forbidden — never the runbook.
        self.assertIn(response.status_code, (302, 403))
        self.assertNotIn(f"--slug {self.SLUG}", response.content.decode("utf-8"))
