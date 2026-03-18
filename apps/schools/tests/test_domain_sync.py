import os
from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.schools.domain_sync import (
    ensure_schooldomain_records_for_school,
    is_runtime_domain_in_use,
    school_subdomain_fqdn,
    sync_verified_schooldomain,
)
from apps.schools.models import School, SchoolDomain


@override_settings(USE_DJANGO_TENANTS=False)
class DomainSyncTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Domain Sync School",
            slug="domain-sync-school",
            subdomain="domain-sync-school",
            is_active=True,
        )

    def test_school_subdomain_fqdn_uses_base_domain(self):
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            self.assertEqual(
                school_subdomain_fqdn(self.school),
                "domain-sync-school.runmycampus.com",
            )

    def test_ensure_schooldomain_records_creates_verified_subdomain_row(self):
        with patch.dict(
            os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            ensure_schooldomain_records_for_school(self.school)
        row = SchoolDomain.objects.get(
            school=self.school, kind=SchoolDomain.Kind.SUBDOMAIN
        )
        self.assertEqual(row.domain, "domain-sync-school.runmycampus.com")
        self.assertTrue(row.is_verified)

    def test_sync_verified_custom_domain_updates_legacy_school_fields(self):
        row = SchoolDomain.objects.create(
            school=self.school,
            domain="portal.domain-sync.edu",
            kind=SchoolDomain.Kind.CUSTOM,
            is_verified=True,
        )
        sync_verified_schooldomain(row)
        self.school.refresh_from_db()
        self.assertEqual(self.school.custom_domain, "portal.domain-sync.edu")
        self.assertTrue(self.school.custom_domain_verified)

    def test_runtime_domain_check_is_false_without_tenant_mode(self):
        self.assertFalse(
            is_runtime_domain_in_use("portal.domain-sync.edu", school=self.school)
        )
