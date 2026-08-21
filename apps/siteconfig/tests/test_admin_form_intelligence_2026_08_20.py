from __future__ import annotations

from datetime import date
import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.academics.admin import NativeAdminDateWidget
from apps.academics.models import AcademicYear
from apps.academics.structure_provisioning import forecast_academic_year
from apps.schools.models import School
from apps.siteconfig.admin_form_intelligence import (
    AdminFieldVisibilityService,
    MAX_HIDDEN_FIELDS,
    MAX_PREFERENCE_PAYLOAD_BYTES,
    _surface_key,
    admin_field_preferences_view,
    build_admin_field_contract,
)
from apps.siteconfig.models import SiteSettings
from config.admin import platform_admin_site, tenant_admin_site


class AdminFormIntelligenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="admin-form-intelligence",
            email="admin-form-intelligence@example.test",
            password="test-only-password",
        )
        cls.school = School.objects.create(
            name="Form Intelligence School",
            slug="form-intelligence",
            subdomain="form-intelligence",
            country_code="CM",
            is_active=True,
        )

    def _request(self, *, host="form-intelligence.runmycampus.com", method="get", data=None):
        factory = RequestFactory()
        request = getattr(factory, method)(
            "/admin/field-preferences/",
            data=data or {},
            content_type="application/json" if method == "post" else None,
            HTTP_HOST=host,
        )
        request.user = self.user
        request.school = self.school
        request.public_host_kind = "tenant"
        request.urlconf = "config.tenant_urls"
        SessionMiddleware(lambda current_request: None).process_request(request)
        return request

    def test_every_registration_inherits_shared_automation(self):
        gaps = []
        for label, site in (("tenant", tenant_admin_site), ("operator", platform_admin_site)):
            for model, model_admin in site._registry.items():
                if not getattr(model_admin, "_rmc_admin_form_automation", False):
                    gaps.append(f"{label}:{model._meta.label_lower}")
        self.assertEqual(gaps, [])

    def test_all_operator_and_tenant_add_forms_resolve_and_tenant_school_is_excluded(self):
        errors = []
        for label, site, host, urlconf, school in (
            (
                "tenant",
                tenant_admin_site,
                "form-intelligence.runmycampus.com",
                "config.tenant_urls",
                self.school,
            ),
            (
                "operator",
                platform_admin_site,
                "manager.runmycampus.com",
                "config.urls",
                None,
            ),
        ):
            request = self._request(host=host)
            request.school = school
            request.public_host_kind = "tenant" if label == "tenant" else "manager"
            request.urlconf = urlconf
            for model, model_admin in site._registry.items():
                try:
                    form_class = model_admin.get_form(
                        request, obj=None, change=False
                    )
                except Exception as exc:  # pragma: no cover - failure ledger
                    errors.append(
                        f"{label}:{model._meta.label_lower}:{type(exc).__name__}:{exc}"
                    )
                    continue
                has_school = any(field.name == "school" for field in model._meta.fields)
                if label == "tenant" and has_school and "school" in form_class.base_fields:
                    errors.append(f"{label}:{model._meta.label_lower}:school-editable")
        self.assertEqual(errors, [])

    def test_forecast_uses_history_and_remains_a_plain_initial(self):
        AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 8, 31),
            is_active=True,
        )
        forecast = forecast_academic_year(self.school, today=date(2026, 8, 20))
        self.assertEqual(forecast["name"], "2026/2027")
        self.assertEqual(forecast["start_date"], date(2026, 9, 1))
        self.assertEqual(forecast["end_date"], date(2027, 8, 31))
        self.assertFalse(forecast["is_active"])

        model_admin = tenant_admin_site._registry[AcademicYear]
        request = self._request()
        initial = model_admin.get_changeform_initial_data(request)
        self.assertEqual(initial["name"], "2026/2027")
        self.assertEqual(initial["school"], self.school.pk)

    def test_native_date_widget_has_no_javascript_only_dependency(self):
        widget = NativeAdminDateWidget()
        self.assertEqual(widget.input_type, "date")
        html = widget.render("start_date", date(2026, 9, 1))
        self.assertIn('type="date"', html)
        self.assertIn('value="2026-09-01"', html)

    def test_academic_year_model_rejects_invalid_overlap_and_second_active(self):
        first = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 8, 31),
            is_active=True,
        )
        invalid = AcademicYear(
            school=self.school,
            name="invalid",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 1),
        )
        with self.assertRaises(ValidationError):
            invalid.full_clean()

        overlap = AcademicYear(
            school=self.school,
            name="overlap",
            start_date=date(2026, 8, 1),
            end_date=date(2027, 7, 31),
        )
        with self.assertRaises(ValidationError) as caught:
            overlap.full_clean()
        self.assertIn("start_date", caught.exception.message_dict)

        second_active = AcademicYear(
            school=self.school,
            name="2026/2027",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 8, 31),
            is_active=True,
        )
        with self.assertRaises(ValidationError) as caught:
            second_active.full_clean()
        self.assertIn("is_active", caught.exception.message_dict)
        first.delete()

    def test_preferences_are_separate_by_host_site_model_and_mode(self):
        tenant_key = _surface_key(
            host="form-intelligence.runmycampus.com",
            admin_site_name="tenant_admin",
            model_label="academics.academicyear",
            mode="add",
        )
        operator_key = _surface_key(
            host="manager.runmycampus.com",
            admin_site_name="admin",
            model_label="academics.academicyear",
            mode="add",
        )
        AdminFieldVisibilityService.write(
            user=self.user,
            surface_key=tenant_key,
            hidden_fields=["enable_gce_registration"],
            allowed_optional_fields=["enable_gce_registration"],
        )
        self.assertEqual(
            AdminFieldVisibilityService.read(user=self.user, surface_key=tenant_key)[
                "hidden"
            ],
            ["enable_gce_registration"],
        )
        self.assertEqual(
            AdminFieldVisibilityService.read(user=self.user, surface_key=operator_key), {}
        )

    def test_mandatory_or_unknown_field_cannot_be_hidden(self):
        key = _surface_key(
            host="form-intelligence.runmycampus.com",
            admin_site_name="tenant_admin",
            model_label="academics.academicyear",
            mode="add",
        )
        with self.assertRaises(ValidationError):
            AdminFieldVisibilityService.write(
                user=self.user,
                surface_key=key,
                hidden_fields=["name"],
                allowed_optional_fields=["enable_gce_registration"],
            )

    def test_tenant_contract_hides_school_but_keeps_suggestions_editable(self):
        model_admin = tenant_admin_site._registry[AcademicYear]
        request = self._request()
        form_class = model_admin.get_form(request)
        contract = build_admin_field_contract(model_admin, request)
        optional_names = {item["name"] for item in contract.optional_fields}
        self.assertIn("school", contract.system_hidden_fields)
        self.assertNotIn("school", optional_names)
        self.assertIn("name", contract.required_fields)
        self.assertIn("name", contract.recommended_fields)
        self.assertIn("start_date", contract.recommended_fields)
        self.assertIn("end_date", contract.recommended_fields)
        self.assertNotIn("client_offline_id", contract.recommended_fields)
        self.assertNotIn("client_offline_id", form_class.base_fields)
        self.assertIn(
            "client_offline_id", model_admin.get_readonly_fields(request, None)
        )
        self.assertIn("enable_gce_registration", optional_names)

    def test_specialized_contract_only_advertises_fields_rendered_by_its_fieldsets(self):
        model_admin = tenant_admin_site._registry[SiteSettings]
        request = self._request()
        form = model_admin.get_form(request)(instance=SiteSettings())
        self.assertIn("txp_use_v3_shell", form.fields)

        contract = build_admin_field_contract(model_admin, request, mode="change")
        editable = set(contract.required_fields)
        editable.update(item["name"] for item in contract.optional_fields)

        self.assertNotIn("txp_use_v3_shell", editable)
        self.assertNotIn("txp_use_v3_shell", contract.recommended_fields)
        self.assertIn("maintenance_mode", editable)
        self.assertTrue(set(contract.recommended_fields).issubset(editable))

    def test_endpoint_persists_only_valid_optional_fields(self):
        body = {
            "model": "academics.academicyear",
            "mode": "add",
            "hidden": ["enable_gce_registration"],
        }
        request = self._request(method="post", data=body)
        response = admin_field_preferences_view(
            request, admin_site=tenant_admin_site
        )
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["hidden"], ["enable_gce_registration"])

    def test_endpoint_rejects_non_object_and_non_list_payloads(self):
        request = self._request(method="post", data=["not", "an", "object"])
        response = admin_field_preferences_view(
            request, admin_site=tenant_admin_site
        )
        self.assertEqual(response.status_code, 400)

    def test_endpoint_rejects_ambiguous_reset_and_bounded_payloads(self):
        request = self._request(
            method="post",
            data={
                "model": "academics.academicyear",
                "mode": "add",
                "hidden": [],
                "reset": "false",
            },
        )
        response = admin_field_preferences_view(
            request, admin_site=tenant_admin_site
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("JSON boolean", json.loads(response.content)["error"])

        request = self._request(
            method="post",
            data={
                "model": "academics.academicyear",
                "mode": "add",
                "hidden": [f"field_{index}" for index in range(MAX_HIDDEN_FIELDS + 1)],
            },
        )
        response = admin_field_preferences_view(
            request, admin_site=tenant_admin_site
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("At most", json.loads(response.content)["error"])

        factory = RequestFactory()
        request = factory.generic(
            "POST",
            "/admin/field-preferences/",
            data=b"{" + (b" " * MAX_PREFERENCE_PAYLOAD_BYTES) + b"}",
            content_type="application/json",
            HTTP_HOST="form-intelligence.runmycampus.com",
        )
        request.user = self.user
        request.school = self.school
        request.urlconf = "config.tenant_urls"
        response = admin_field_preferences_view(
            request, admin_site=tenant_admin_site
        )
        self.assertEqual(response.status_code, 413)

        request = self._request(
            method="post",
            data={
                "model": "academics.academicyear",
                "mode": "add",
                "hidden": "enable_gce_registration",
            },
        )
        response = admin_field_preferences_view(
            request, admin_site=tenant_admin_site
        )
        self.assertEqual(response.status_code, 400)

    def test_hidden_optional_field_cannot_be_changed_by_crafted_post(self):
        academic_year = AcademicYear.objects.create(
            school=self.school,
            name="2028/2029",
            start_date=date(2028, 9, 1),
            end_date=date(2029, 8, 31),
            is_active=False,
            enable_gce_registration=False,
        )
        request = self._request(method="post")
        key = _surface_key(
            host="form-intelligence.runmycampus.com",
            admin_site_name="tenant_admin",
            model_label="academics.academicyear",
            mode="change",
        )
        AdminFieldVisibilityService.write(
            user=self.user,
            surface_key=key,
            hidden_fields=["enable_gce_registration"],
            allowed_optional_fields=["enable_gce_registration"],
        )
        model_admin = tenant_admin_site._registry[AcademicYear]
        form_class = model_admin.get_form(
            request, obj=academic_year, change=True
        )
        form = form_class(
            data={
                "name": academic_year.name,
                "start_date": academic_year.start_date.isoformat(),
                "end_date": academic_year.end_date.isoformat(),
                "is_active": "",
                "is_locked": "",
                "is_soft_closed": "",
                "enable_gce_registration": "on",
                "lock_reason": "",
                "unlock_reason": "",
                "soft_close_reason": "",
                "soft_reopen_reason": "",
                "client_offline_id": "",
            },
            instance=academic_year,
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertFalse(form.cleaned_data["enable_gce_registration"])
        candidate = form.save(commit=False)
        model_admin.save_model(request, candidate, form, change=True)
        academic_year.refresh_from_db()
        self.assertFalse(academic_year.enable_gce_registration)
        self.assertEqual(academic_year.school, self.school)

    def test_hidden_optional_field_cannot_be_mass_assigned_on_add(self):
        request = self._request(method="post")
        key = _surface_key(
            host="form-intelligence.runmycampus.com",
            admin_site_name="tenant_admin",
            model_label="academics.academicyear",
            mode="add",
        )
        AdminFieldVisibilityService.write(
            user=self.user,
            surface_key=key,
            hidden_fields=["enable_gce_registration"],
            allowed_optional_fields=["enable_gce_registration"],
        )
        model_admin = tenant_admin_site._registry[AcademicYear]
        form_class = model_admin.get_form(request, obj=None, change=False)
        form = form_class(
            data={
                "name": "2030/2031",
                "start_date": "2030-09-01",
                "end_date": "2031-08-31",
                "is_active": "",
                "is_locked": "",
                "is_soft_closed": "",
                "enable_gce_registration": "on",
                "lock_reason": "",
                "unlock_reason": "",
                "soft_close_reason": "",
                "soft_reopen_reason": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertFalse(form.cleaned_data["enable_gce_registration"])
        candidate = form.save(commit=False)
        model_admin.save_model(request, candidate, form, change=False)
        self.assertFalse(candidate.enable_gce_registration)
        self.assertEqual(candidate.school, self.school)

    def test_endpoint_rejects_unknown_mode(self):
        request = self._request(
            method="post",
            data={
                "model": "academics.academicyear",
                "mode": "unexpected",
                "hidden": [],
            },
        )
        response = admin_field_preferences_view(
            request, admin_site=tenant_admin_site
        )
        self.assertEqual(response.status_code, 400)

    def test_obsolete_stored_keys_are_ignored_and_reset_is_scoped(self):
        key = _surface_key(
            host="form-intelligence.runmycampus.com",
            admin_site_name="tenant_admin",
            model_label="academics.academicyear",
            mode="add",
        )
        Preference = AdminFieldVisibilityService._preference_model()
        preference, _ = Preference.objects.get_or_create(user=self.user)
        layout = dict(preference.dashboard_layout or {})
        namespace = dict(layout.get("_rmc_admin_field_visibility_v1") or {})
        namespace[key] = {
            "hidden": ["removed_field", "enable_gce_registration"]
        }
        layout["_rmc_admin_field_visibility_v1"] = namespace
        preference.dashboard_layout = layout
        preference.save(update_fields=["dashboard_layout", "updated_at"])

        contract = build_admin_field_contract(
            tenant_admin_site._registry[AcademicYear], self._request()
        )
        self.assertEqual(contract.hidden_fields, ("enable_gce_registration",))
        AdminFieldVisibilityService.write(
            user=self.user,
            surface_key=key,
            hidden_fields=[],
            allowed_optional_fields=["enable_gce_registration"],
            reset=True,
        )
        self.assertEqual(
            AdminFieldVisibilityService.read(user=self.user, surface_key=key), {}
        )

    def test_persistence_guard_rejects_reversed_range_on_save(self):
        invalid = AcademicYear(
            school=self.school,
            name="reversed",
            start_date=date(2027, 8, 31),
            end_date=date(2026, 9, 1),
        )
        with self.assertRaises(ValidationError):
            invalid.save()
