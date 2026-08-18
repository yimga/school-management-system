"""Tenant School & Region settings editor — the tenant-admin surface that lets a
school edit its registry-backed config (the fields the Setup/Launch "Registry
alignment" table checks), closing the gap where sector / institution type /
timezone / calendar / sub_system / subdivision were operator-only.

These POST tests use RequestFactory (the view redirects on POST — no template
render), which keeps them independent of the full tenant-shell context the GET
render needs. The GET render is covered by verify_template_compiles + boundary
gates.
"""

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.registries.models import (
    CalendarSystemRegistry,
    CountryRegistry,
    CurrencyRegistry,
    EducationSystemTypeRegistry,
    InstitutionTypeRegistry,
    LocaleRegistry,
    SubdivisionRegistry,
    TimeZoneRegistry,
)
from apps.schools.models import School
from apps.siteconfig.views_school_region_settings import school_region_settings
from apps.setup_studio.services import get_setup_studio_payload


def _attach(request):
    SessionMiddleware(lambda r: None).process_request(request)
    request.session.save()
    request._messages = FallbackStorage(request)
    return request


class SchoolRegionSettingsEditorTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.cm, _ = CountryRegistry.objects.get_or_create(
            code="CM", defaults={"name": "Cameroon", "is_active": True}
        )
        SubdivisionRegistry.objects.get_or_create(
            country=self.cm, code="LT", defaults={"name": "Littoral", "is_active": True}
        )
        for code, name in (("UTC", "UTC"), ("Africa/Douala", "West Africa Time")):
            TimeZoneRegistry.objects.get_or_create(
                code=code, defaults={"name": name, "is_active": True}
            )
        CurrencyRegistry.objects.get_or_create(
            code="XAF", defaults={"name": "CFA Franc BEAC", "is_active": True}
        )
        for code, name in (("en", "English"), ("fr", "French")):
            LocaleRegistry.objects.get_or_create(
                code=code, defaults={"name": name, "is_active": True}
            )
        CalendarSystemRegistry.objects.get_or_create(
            code="gregorian", defaults={"name": "Gregorian (civil)", "is_active": True}
        )
        InstitutionTypeRegistry.objects.get_or_create(
            code="BASE_SCHOOL", defaults={"name": "Base school", "is_active": True}
        )
        # sector rows (primary_sector select) + a curriculum type (M2M)
        EducationSystemTypeRegistry.objects.get_or_create(
            code="PRIVATE",
            defaults={
                "name": "Private / independent",
                "category": "sector",
                "is_active": True,
            },
        )
        EducationSystemTypeRegistry.objects.get_or_create(
            code="PUBLIC",
            defaults={"name": "Public / state", "category": "sector", "is_active": True},
        )
        EducationSystemTypeRegistry.objects.get_or_create(
            code="IB",
            defaults={"name": "IB", "category": "curriculum", "is_active": True},
        )

        self.school = School.objects.create(
            name="Region Editor School",
            slug="region-editor-school",
            subdomain="region-editor-school",
            country_code="CM",
            timezone="UTC",
            school_type="BASE_SCHOOL",
            is_active=True,
        )
        User = get_user_model()
        self.admin = User.objects.create_user(
            username="tenant_admin_srs", password="x" * 10
        )
        self.admin.role = User.Role.ADMIN
        self.admin.save(update_fields=["role"])
        self.rf = RequestFactory()

    def _post(self, data, user=None):
        req = _attach(self.rf.post("/siteconfig/school-region-settings/", data))
        req.user = user or self.admin
        req.school = self.school
        return school_region_settings(req)

    def test_post_updates_model_fields_settings_and_alignment(self):
        resp = self._post(
            {
                "primary_sector": "PRIVATE",
                "timezone": "Africa/Douala",
                "school_type": "BASE_SCHOOL",
                "sub_system": "FR",
                "currency": "XAF",
                "calendar_system": "gregorian",
                "default_language": "fr",
                "subdivision": "LT",
                "education_system_types": ["IB"],
            }
        )
        self.assertEqual(resp.status_code, 302)
        self.school.refresh_from_db()
        # model fields
        self.assertEqual(self.school.primary_sector, "PRIVATE")
        self.assertEqual(self.school.timezone, "Africa/Douala")
        self.assertEqual(self.school.sub_system, "FR")
        self.assertEqual(self.school.currency, "XAF")
        self.assertEqual(getattr(self.school.subdivision, "code", None), "LT")
        self.assertIn(
            "IB", set(self.school.education_system_types.values_list("code", flat=True))
        )
        # settings keys
        self.assertEqual(self.school.settings.get("default_currency"), "XAF")
        self.assertEqual(self.school.settings.get("calendar_system"), "gregorian")
        self.assertEqual(self.school.settings.get("default_language"), "fr")
        # end-to-end: the education-system alignment row now reflects the tenant's
        # own edit (reads primary_sector), so the once-unfixable warning clears.
        ra = get_setup_studio_payload(self.school)["registry_alignment"]
        self.assertEqual(ra.get("education_system_code"), "PRIVATE")
        self.assertTrue(ra.get("education_system_type_registry_ok"))

    def test_invalid_registry_code_is_ignored(self):
        self._post({"primary_sector": "NOT_A_REAL_SECTOR"})
        self.school.refresh_from_db()
        self.assertNotEqual(self.school.primary_sector, "NOT_A_REAL_SECTOR")

    def test_non_admin_is_forbidden(self):
        User = get_user_model()
        pupil = User.objects.create_user(username="pupil_srs", password="x" * 10)
        pupil.role = User.Role.STUDENT
        pupil.save(update_fields=["role"])
        with self.assertRaises(PermissionDenied):
            self._post({"primary_sector": "PRIVATE"}, user=pupil)

    def test_missing_school_redirects(self):
        req = _attach(self.rf.post("/siteconfig/school-region-settings/", {}))
        req.user = self.admin
        req.school = None
        resp = school_region_settings(req)
        self.assertEqual(resp.status_code, 302)

    def test_named_url_resolves(self):
        url = reverse("siteconfig:school_region_settings")
        self.assertTrue(url.endswith("school-region-settings/"))
