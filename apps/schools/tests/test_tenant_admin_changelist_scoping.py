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

    # --- FK / M2M form-field scoping (the Add-form dropdown seal) ---------------
    # The changelist seal above scopes get_queryset (LIST views); a FK OPTION LIST
    # in an add/change FORM is a separate code path (formfield_for_foreignkey) that
    # was NOT scoped — so Add Academic Year's ``School`` picker listed every tenant's
    # school (the reported cross-tenant leak). These lock the form path.

    @staticmethod
    def _school_db_field():
        return AcademicYear._meta.get_field("school")

    def _add_req(self, school):
        req = RequestFactory().get("/admin/academics/academicyear/add/")
        req.school = school
        req.user = self.superuser
        return req

    def test_school_fk_formfield_scoped_to_own_school(self):
        ma = tenant_admin_site._registry[AcademicYear]
        self.assertTrue(
            getattr(ma, "_rmc_tenant_fk_scoped", False),
            "AcademicYear tenant admin lacks FK-form scoping",
        )
        ff_a = ma.formfield_for_foreignkey(self._school_db_field(), self._add_req(self.school_a))
        options_a = set(ff_a.queryset.values_list("name", flat=True))
        self.assertEqual(
            options_a, {"Alpha"},
            f"School picker leaked cross-tenant schools on school_a: {options_a}",
        )
        # Pre-selects the tenant's own school (context comes from the header, not a pick).
        self.assertEqual(ff_a.initial, self.school_a.pk)

        ff_b = ma.formfield_for_foreignkey(self._school_db_field(), self._add_req(self.school_b))
        self.assertEqual(set(ff_b.queryset.values_list("name", flat=True)), {"Beta"})

    def test_school_fk_fails_closed_when_tenant_indeterminate(self):
        # A tenant form must NEVER fall back to every tenant's rows.
        ma = tenant_admin_site._registry[AcademicYear]
        req = RequestFactory().get("/admin/academics/academicyear/add/")
        req.user = self.superuser
        req.school = None
        ff = ma.formfield_for_foreignkey(self._school_db_field(), req)
        self.assertEqual(
            ff.queryset.count(), 0,
            "School picker must fail closed (show nothing) when the tenant is indeterminate",
        )

    def test_every_tenant_admin_has_fk_form_scope(self):
        # Structural guarantee: EVERY tenant-admin model carries the FK-form seal,
        # so a future registration can't slip a cross-tenant FK picker past it.
        ungated = [
            model._meta.label
            for model, ma in tenant_admin_site._registry.items()
            if not getattr(ma, "_rmc_tenant_fk_scoped", False)
        ]
        self.assertEqual(ungated, [], f"tenant admins missing FK-form scope: {ungated}")

    def test_platform_admin_school_fk_not_scoped(self):
        # Operators must still pick ANY school on the platform admin.
        ma = platform_admin_site._registry.get(AcademicYear)
        if ma is not None:
            self.assertFalse(getattr(ma, "_rmc_tenant_fk_scoped", False))
            ff = ma.formfield_for_foreignkey(self._school_db_field(), self._add_req(self.school_a))
            names = set(ff.queryset.values_list("name", flat=True))
            self.assertIn("Beta", names)  # operator sees the OTHER school too
