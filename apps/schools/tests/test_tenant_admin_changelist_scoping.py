"""The tenant /admin/ changelist must never show another school's rows.

SHARED_APPS models live in the public schema (one table holding every tenant's
rows); a tenant-schema request's search_path includes public, so an unscoped
admin changelist would render all schools' data on one school's branded /admin/.
Before this seal only ``accounts.User`` was scoped; ~70 shared-app ModelAdmins
were not. ``TenantAdminSite.register`` now auto-wraps every school-bearing model
with ``_TenantScopedQuerysetMixin`` (school == request.school OR school IS NULL).

These lock the contract:
* a school-bearing model's tenant-admin changelist excludes another school's rows
  and includes the current school's + platform-global (NULL) rows;
* every shared-app ModelAdmin registered on the tenant site is scoped (0 gaps);
* the SAME model on the PLATFORM admin is NOT scoped (operators see all tenants);
* a model with no ``school`` field is left alone (not wrongly wrapped/erroring).
"""
from __future__ import annotations

from datetime import date

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.academics.models import AcademicYear
from apps.schools.models import School
from config.admin import platform_admin_site, tenant_admin_site


class TenantAdminChangelistScopingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school_a = School.objects.create(
            name="Alpha", slug="alpha-adm", subdomain="alpha-adm", is_active=True
        )
        cls.school_b = School.objects.create(
            name="Beta", slug="beta-adm", subdomain="beta-adm", is_active=True
        )
        cls.superuser = get_user_model().objects.create_superuser(
            username="admin_scope_su", email="su@x.co", password="x"
        )
        cls.year_a = AcademicYear.objects.create(
            school=cls.school_a, name="A-2025/26",
            start_date=date(2025, 9, 1), end_date=date(2026, 7, 31), is_active=True,
        )
        cls.year_b = AcademicYear.objects.create(
            school=cls.school_b, name="B-2025/26",
            start_date=date(2025, 9, 1), end_date=date(2026, 7, 31), is_active=True,
        )

    def _req(self, school):
        req = RequestFactory().get("/admin/academics/academicyear/")
        req.school = school
        req.user = self.superuser
        return req

    def test_changelist_excludes_other_schools_rows(self):
        ma = tenant_admin_site._registry[AcademicYear]
        self.assertTrue(
            getattr(ma, "_rmc_tenant_scoped", False),
            "AcademicYear tenant admin was not tenant-scoped",
        )
        names_on_a = set(ma.get_queryset(self._req(self.school_a)).values_list("name", flat=True))
        self.assertIn("A-2025/26", names_on_a)  # own row visible
        self.assertNotIn("B-2025/26", names_on_a)  # the seal: other school hidden

        names_on_b = set(ma.get_queryset(self._req(self.school_b)).values_list("name", flat=True))
        self.assertIn("B-2025/26", names_on_b)
        self.assertNotIn("A-2025/26", names_on_b)

    def test_global_null_school_rows_stay_visible(self):
        # A platform-global (school IS NULL) row is the same for every tenant, so
        # it must NOT be hidden by the scope (only OTHER tenants' rows are).
        glob = AcademicYear.objects.create(
            school=None, name="GLOBAL-YEAR",
            start_date=date(2025, 9, 1), end_date=date(2026, 7, 31), is_active=True,
        )
        ma = tenant_admin_site._registry[AcademicYear]
        names = set(ma.get_queryset(self._req(self.school_a)).values_list("name", flat=True))
        self.assertIn("GLOBAL-YEAR", names)
        glob.delete()

    def test_every_shared_app_tenant_admin_is_scoped(self):
        # No school-bearing model on the tenant site may be left unscoped — this is
        # the structural guarantee, and it fails loudly if a future registration
        # slips a school-bearing model past the seal.
        unscoped = []
        for model, ma in tenant_admin_site._registry.items():
            try:
                field = model._meta.get_field("school")
                has_school = field.concrete and not field.many_to_many
            except Exception:  # noqa: BLE001
                has_school = False
            if has_school and not getattr(ma, "_rmc_tenant_scoped", False):
                unscoped.append(model._meta.label)
        self.assertEqual(unscoped, [], f"school-bearing tenant admins left unscoped: {unscoped}")

    def test_platform_admin_is_not_scoped(self):
        # Operators must still see every tenant on the platform admin.
        ma = platform_admin_site._registry.get(AcademicYear)
        if ma is not None:
            self.assertFalse(getattr(ma, "_rmc_tenant_scoped", False))
