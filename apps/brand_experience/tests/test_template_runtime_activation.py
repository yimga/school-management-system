from __future__ import annotations

from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.contrib.sessions.backends.signed_cookies import SessionStore
from django.test import RequestFactory, TestCase
from django.urls import set_urlconf

from apps.brand_experience.models_template import TemplateAssignment
from apps.brand_experience.tests.test_template_marketplace_semantic_runtime import (
    _attach_tenant,
    _bootstrap_tenant_school,
)
from apps.brand_experience.views_template_marketplace import (
    tenant_template_apply,
    tenant_template_preview,
)
from apps.packages.models import InstalledPackage
from apps.platform_runtime.pack_apply import apply_pack
from apps.platform_runtime.pack_impact import analyze_pack_impact
from apps.platform_runtime.pack_preview import preview_pack
from apps.platform_runtime.pack_simulation import simulate_pack
from apps.platform_runtime.models import PackInstallation
from apps.platform_runtime.live_preview import get_preview_url
from apps.platform_runtime.pack_rollback import rollback_pack_installation
from apps.setup_studio.services import get_setup_studio_payload
from apps.siteconfig.feature_toggles import set_toggle_state


User = get_user_model()
TEMPLATE_KEY = "admin-school-command-center"
PREVIOUS_TEMPLATE_KEY = "admin-academic-ops-hub"


class ExperienceTemplateRuntimeActivationTests(TestCase):
    def setUp(self):
        self.school = _bootstrap_tenant_school(slug="experience-runtime")
        self.user = User.objects.create_user(
            username="experience-admin",
            email="experience@example.com",
            password="x",
            role=User.Role.ADMIN,
        )
        self.rf = RequestFactory()

    def tearDown(self):
        set_urlconf(None)

    def _request(self, *, method="get", path="/school/studio/templates/"):
        request = getattr(self.rf, method)(
            path,
            {"confirm": "yes"} if method == "post" else {},
            HTTP_HOST=f"{self.school.slug}.runmycampus.com",
        )
        request.session = SessionStore()
        request.public_host_kind = "tenant"
        return _attach_tenant(request, user=self.user, school=self.school)

    def _apply(self, template_key=TEMPLATE_KEY):
        preview = preview_pack(
            template_key,
            pack_type="experience_template",
            school=self.school,
            actor=self.user,
        )
        simulation = simulate_pack(
            template_key,
            pack_type="experience_template",
            school=self.school,
            actor=self.user,
        )
        impact = analyze_pack_impact(
            template_key,
            pack_type="experience_template",
            school=self.school,
            actor=self.user,
        )
        return apply_pack(
            template_key,
            pack_type="experience_template",
            school=self.school,
            actor=self.user,
            preview_snapshot=preview,
            simulation_snapshot=simulation,
            impact_snapshot=impact,
            confirmed=True,
        )

    def test_apply_activates_assignment_runtime_and_checklist(self):
        result = self._apply()
        self.assertTrue(result["ok"], result)
        self.assertIsNotNone(result["experience_runtime"])
        assignment = TemplateAssignment.objects.get(
            template_key=TEMPLATE_KEY,
            installed_package__school=self.school,
        )
        self.assertTrue(assignment.installed_package.is_active)
        self.assertEqual(assignment.installed_package.package_type, "experience_pack")
        self.school.refresh_from_db()
        runtime = self.school.settings["active_experience_templates"]["tenant-admin"]
        self.assertEqual(runtime["template_key"], TEMPLATE_KEY)
        payload = get_setup_studio_payload(self.school)
        step = next(row for row in payload["steps"] if row["key"] == "select_experience_template")
        self.assertTrue(step["done"])

    def test_reapply_is_idempotent_but_repairs_runtime(self):
        first = self._apply()
        self.school.refresh_from_db()
        settings = dict(self.school.settings)
        settings.pop("active_experience_templates", None)
        self.school.settings = settings
        self.school.save(update_fields=["settings"])
        TemplateAssignment.objects.all().delete()

        second = self._apply()

        self.assertTrue(first["ok"])
        self.assertTrue(second["ok"])
        self.assertTrue(second["idempotent"])
        self.assertIsNotNone(second["experience_runtime"])
        self.assertEqual(TemplateAssignment.objects.count(), 1)

    def test_starter_stack_uses_canonical_module_toggle(self):
        set_toggle_state("module.academics", enabled=True, school=self.school, user=self.user)
        payload = get_setup_studio_payload(self.school)
        step = next(row for row in payload["steps"] if row["key"] == "starter_stack")
        self.assertTrue(step["done"])

    def test_preview_uses_real_same_origin_target(self):
        response = tenant_template_preview(self._request(), key=TEMPLATE_KEY)
        body = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn('data-rmc-preview-frame', body)
        self.assertIn('rmc_embed=1', body)
        self.assertNotIn('/portal/preview?', body)
        self.assertIn('/authentication/backend/', body)
        self.assertIn('Open full preview', body)

    def test_preview_normalizes_only_matching_absolute_tenant_urls(self):
        self.assertTrue(
            get_preview_url(
                path="https://experience-runtime.runmycampus.com/authentication/backend/",
                role="admin",
                origin_host="experience-runtime.runmycampus.com:443",
            ).startswith("/authentication/backend/")
        )
        self.assertIsNone(
            get_preview_url(
                path="https://evil.example/authentication/backend/",
                role="admin",
                origin_host="experience-runtime.runmycampus.com",
            )
        )

    def test_success_page_no_longer_asks_for_confirmation(self):
        response = tenant_template_apply(
            self._request(method="post", path=f"/school/studio/templates/{TEMPLATE_KEY}/apply/"),
            key=TEMPLATE_KEY,
        )
        body = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Template active", body)
        self.assertIn("Review launch checklist", body)
        self.assertIn(f'data-rmc-experience-template="{TEMPLATE_KEY}"', body)
        self.assertNotIn("Confirm impact before applying", body)

    def test_rollback_clears_runtime_and_checklist_completion(self):
        result = self._apply()
        installation = PackInstallation.objects.get(pk=result["installation_id"])

        rollback_result = rollback_pack_installation(
            installation,
            actor=self.user,
            confirmed=True,
        )

        self.assertTrue(rollback_result["ok"])
        installation.refresh_from_db()
        self.assertEqual(installation.status, PackInstallation.Status.ROLLED_BACK)
        self.school.refresh_from_db()
        self.assertFalse(self.school.settings.get("active_experience_templates"))
        payload = get_setup_studio_payload(self.school)
        step = next(row for row in payload["steps"] if row["key"] == "select_experience_template")
        self.assertFalse(step["done"])

    def test_rollback_reactivates_the_previous_template_on_the_same_surface(self):
        previous_result = self._apply(PREVIOUS_TEMPLATE_KEY)
        current_result = self._apply(TEMPLATE_KEY)
        previous_assignment = TemplateAssignment.objects.get(
            installed_package_id=previous_result["experience_runtime"]["installed_package_id"]
        )
        previous_assignment.installed_package.refresh_from_db()
        self.assertFalse(previous_assignment.installed_package.is_active)

        rollback_result = rollback_pack_installation(
            PackInstallation.objects.get(pk=current_result["installation_id"]),
            actor=self.user,
            confirmed=True,
        )

        self.assertTrue(rollback_result["ok"])
        previous_assignment.installed_package.refresh_from_db()
        self.assertTrue(previous_assignment.installed_package.is_active)
        self.school.refresh_from_db()
        restored = self.school.settings["active_experience_templates"]["tenant-admin"]
        self.assertEqual(restored["template_key"], PREVIOUS_TEMPLATE_KEY)

    def test_package_type_is_not_misclassified_as_blueprint(self):
        self._apply()
        installed = InstalledPackage.objects.get(
            school=self.school,
            package_id=f"experience_template:{TEMPLATE_KEY}",
        )
        self.assertEqual(installed.package_type, "experience_pack")

    def test_reconciliation_command_audits_then_repairs_existing_apply(self):
        self._apply()
        self.school.refresh_from_db()
        settings = dict(self.school.settings)
        settings.pop("active_experience_templates", None)
        self.school.settings = settings
        self.school.save(update_fields=["settings"])
        TemplateAssignment.objects.all().delete()

        audit_output = StringIO()
        call_command(
            "reconcile_experience_template_runtime",
            school=self.school.slug,
            stdout=audit_output,
        )
        self.assertIn("NEEDS_REPAIR", audit_output.getvalue())
        self.assertFalse(TemplateAssignment.objects.exists())

        apply_output = StringIO()
        call_command(
            "reconcile_experience_template_runtime",
            school=self.school.slug,
            apply=True,
            stdout=apply_output,
        )
        self.assertIn("repaired=1", apply_output.getvalue())
        self.assertTrue(TemplateAssignment.objects.exists())
        self.school.refresh_from_db()
        self.assertIn("active_experience_templates", self.school.settings)
