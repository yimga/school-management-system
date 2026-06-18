"""Wizard index tile navigation — every Start/Review card must reach the wizard shell."""

from __future__ import annotations

from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.registries.models import CountryRegistry
from apps.schools.models import School
from apps.setup_studio import wizard_engine, wizard_views
from apps.setup_studio.models import SetupProgress
from apps.setup_studio.sovereignty_kernel import ensure_sovereignty_kernel_for_tenant


def _mark_wizard_completed_for_tests(school: School, wizard_key: str) -> None:
    progress, _ = SetupProgress.objects.get_or_create(school=school)
    state = dict(progress.step_state or {})
    wizards = dict(state.get("wizards") or {})
    wizards[wizard_key] = {
        "completed_at": "2026-06-17T00:00:00Z",
        "completed": ["test_seed"],
        "answers": {},
    }
    state["wizards"] = wizards
    progress.step_state = state
    progress.save(update_fields=["step_state"])


def _seed_tenant_wizard_gate_fixtures(school: School) -> None:
    """Operational kernel + prerequisite completion so reachability tests hit the shell."""
    ensure_sovereignty_kernel_for_tenant(school=school)
    prereq_keys: set[str] = set()
    for wizard in wizard_engine.list_wizards_for_audience("tenant_admin"):
        prereq = (wizard.gates or {}).get("prerequisite_wizard")
        if prereq:
            prereq_keys.add(str(prereq))
    for key in sorted(prereq_keys):
        _mark_wizard_completed_for_tests(school, key)

User = get_user_model()


class TenantWizardHrefTemplateTests(TestCase):
    def test_href_template_uses_named_route(self):
        tpl = wizard_views._tenant_wizard_href_template()
        self.assertIn("{key}", tpl)
        self.assertTrue(tpl.endswith("/"))
        resolved = tpl.replace("{key}", "mfa_setup")
        self.assertEqual(
            resolved,
            reverse("setup_studio:tenant_wizard", kwargs={"wizard_key": "mfa_setup"}),
        )


class CompletedWizardReviewTests(TestCase):
    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Review School",
            slug="review-school",
            subdomain="review-school",
            country_code="CM",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="review-admin",
            password="Test1234!",
            role="ADMIN",
        )
        progress, _ = SetupProgress.objects.get_or_create(school=self.school)
        progress.step_state = {
            "wizards": {
                "mfa_setup": {
                    "completed_at": "2026-06-16T00:00:00Z",
                    "completed": ["enable_mfa"],
                    "answers": {"enable_mfa": {"value": True}},
                }
            }
        }
        progress.save(update_fields=["step_state"])

    def test_completed_wizard_get_renders_review_shell_not_index(self):
        request = RequestFactory().get(
            reverse("setup_studio:tenant_wizard", kwargs={"wizard_key": "mfa_setup"})
        )
        request.user = self.user
        request.school = self.school
        request.session = {}

        response = wizard_views.TenantWizardView.as_view()(
            request, wizard_key="mfa_setup"
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("rmc-wizard-review-banner", content)
        self.assertNotIn("rmc-wz-index", content)
        self.assertIn("rmc-wizard-shell", content)


class TenantWizardTileReachabilityTests(TestCase):
    """Each tenant_admin wizard key must GET 200 when school is bound."""

    def setUp(self):
        CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
        self.school = School.objects.create(
            name="Tile School",
            slug="tile-school",
            subdomain="tile-school",
            country_code="CM",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="tile-admin",
            password="Test1234!",
            role="ADMIN",
        )
        _seed_tenant_wizard_gate_fixtures(self.school)

    def test_every_tenant_admin_wizard_renders_wizard_shell(self):
        keys = [
            w.wizard_key
            for w in wizard_engine.list_wizards_for_audience("tenant_admin")
        ]
        self.assertGreaterEqual(len(keys), 18)
        view = wizard_views.TenantWizardView.as_view()
        for wizard_key in keys:
            with self.subTest(wizard_key=wizard_key):
                request = RequestFactory().get(
                    reverse(
                        "setup_studio:tenant_wizard",
                        kwargs={"wizard_key": wizard_key},
                    )
                )
                request.user = self.user
                request.school = self.school
                request.session = {}
                response = view(request, wizard_key=wizard_key)
                self.assertEqual(response.status_code, 200, wizard_key)
                content = response.content.decode()
                self.assertIn("rmc-wizard-shell", content, wizard_key)
                self.assertNotIn("rmc-wz-index", content, wizard_key)


class ResolveSchoolFallbackTests(TestCase):
    def test_session_school_id_resolves_when_request_school_missing(self):
        user = SimpleNamespace(is_authenticated=True, pk=1)
        request = SimpleNamespace(
            school=None,
            tenant=None,
            user=user,
            session={"school_id": "abc-123"},
        )
        fake_school = SimpleNamespace(pk="abc-123", is_active=True)

        with mock.patch(
            "apps.lifecycle.tenant_school_resolve.resolve_request_school",
            return_value=None,
        ), mock.patch(
            "apps.schools.session_school_bind.verify_session_school_bind",
            return_value=True,
        ), mock.patch("apps.schools.models.School") as school_model:
            school_model.objects.filter.return_value.first.return_value = fake_school
            resolved = wizard_views._resolve_school(request)

        self.assertIs(resolved, fake_school)
        school_model.objects.filter.assert_called_with(pk="abc-123", is_active=True)
