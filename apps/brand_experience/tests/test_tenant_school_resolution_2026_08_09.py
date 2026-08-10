"""Seal: _tenant_school returns the School, never the django-tenants Client.

Production 500 (2026-08-09) on POST /school/studio/templates/<key>/apply/:

    ValueError: Cannot query "s_f984ea95d2ad4900b51366a345928316":
                Must be "School" instance.

TENANT_MODEL is customers.Client, so request.tenant is the Client (its __str__
is the schema name s_<hex>), NOT a School. The confirm-apply path passes the
resolved object to apply_pack -> PackInstallation.objects.filter(school=...),
which requires a schools.School instance. _tenant_school used
``request.tenant or request.school`` — and request.tenant (the Client) is always
truthy, so it returned the Client and every apply POST 500'd. The fix prefers
request.school (set by the schools bridge middleware to request.tenant.school)
and falls back to request.tenant.school, so a School is always returned.

These use lightweight fakes (SimpleNamespace) because _tenant_school only does
attribute access — no DB or tenant schema needed (the test harness can't create
tenant schemas anyway).
"""

from types import SimpleNamespace

from django.http import Http404
from django.test import SimpleTestCase

from apps.brand_experience.views_template_marketplace import _tenant_school


class TenantSchoolResolutionTest(SimpleTestCase):
    def test_prefers_request_school_over_the_client_tenant(self):
        # The bug: request.tenant (Client) is truthy, so the old
        # `request.tenant or request.school` returned it. Must return the School.
        school = SimpleNamespace(kind="School")
        client = SimpleNamespace(kind="Client", school=school)  # request.tenant
        request = SimpleNamespace(school=school, tenant=client)

        resolved = _tenant_school(request)

        self.assertIs(resolved, school)
        self.assertIsNot(resolved, client, "must not return the django-tenants Client")

    def test_falls_back_to_tenant_dot_school_when_request_school_absent(self):
        # If the bridge middleware didn't set request.school, resolve the Client's
        # OneToOne .school rather than the Client itself.
        school = SimpleNamespace(kind="School")
        client = SimpleNamespace(kind="Client", school=school)
        request = SimpleNamespace(tenant=client)  # no .school attribute

        self.assertIs(_tenant_school(request), school)

    def test_404_when_no_school_resolvable_anywhere(self):
        request = SimpleNamespace(tenant=SimpleNamespace(kind="Client"))  # tenant has no .school
        with self.assertRaises(Http404):
            _tenant_school(request)
