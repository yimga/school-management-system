"""
Tests for tenant isolation, provisioning job, single-tenant fallback, and feature-flag enforcement (Option B+C).
"""
import json
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.registries.models import (
    CountryRegistry,
    EducationLevelRegistry,
    EducationSystemTypeRegistry,
    SubdivisionRegistry,
)
from apps.schools.models import School, SchoolMembership, SchoolProvisioningEvent
from apps.schools.tasks import provision_school_sync
from apps.people.models import StudentProfile
from apps.academics.models import AcademicYear, Term, Subject
from apps.siteconfig.models import EducationSystemProfile, RegionConfig, TenantSystem, SystemFeature
from apps.siteconfig.global_catalog import GlobalGeoCatalog


class TenantIsolationTests(TestCase):
    """Ensure user in school A cannot read/write school B data."""

    def setUp(self):
        self.client = Client()
        self.school_a = School.objects.create(
            name="School A",
            slug="school-a",
            subdomain="school-a",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="School B",
            slug="school-b",
            subdomain="school-b",
            is_active=True,
        )
        self.user_a = User.objects.create_user(
            username="usera",
            email="usera@test.com",
            password="testpass123",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(user=self.user_a, school=self.school_a, role=User.Role.ADMIN, is_primary=True)
        self.user_b = User.objects.create_user(
            username="userb",
            email="userb@test.com",
            password="testpass123",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(user=self.user_b, school=self.school_b, role=User.Role.ADMIN, is_primary=True)
        self.student_b = StudentProfile.objects.create(
            school=self.school_b,
            first_name="Bob",
            last_name="B",
            student_code="B001",
        )

    def test_api_entity_students_scoped_by_school(self):
        """Students API does not return school B's student when request is for school A."""
        self.client.force_login(self.user_a)
        session = self.client.session
        session["school_id"] = str(self.school_a.id)
        session.save()
        resp = self.client.get(reverse("api:entity-student-list"))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        results = data.get("results") if isinstance(data, dict) else (data if isinstance(data, list) else [])
        ids = [s.get("id") for s in results if isinstance(s, dict) and s.get("id") is not None]
        self.assertNotIn(self.student_b.id, ids, "School A user must not see School B student")

    def test_has_feature_respects_tenant_systems(self):
        """Phase G optional: has_feature() returns only features from that school's TenantSystems (no cross-tenant leak)."""
        region = RegionConfig.objects.filter(code="CMR").first() or RegionConfig.objects.create(
            code="CMR", name="Cameroon", default_language="en", timezone="Africa/Douala", grading_scale="0-20"
        )
        profile_workshop, _ = EducationSystemProfile.objects.get_or_create(
            code="test-workshop-profile",
            defaults={
                "name": "Test Workshop",
                "region": region,
                "sub_system": EducationSystemProfile.SubSystem.EN,
                "is_active": True,
                "approval_status": EducationSystemProfile.ApprovalStatus.APPROVED,
            },
        )
        SystemFeature.objects.get_or_create(system=profile_workshop, feature_key="workshop_management")
        profile_basic, _ = EducationSystemProfile.objects.get_or_create(
            code="test-basic-profile",
            defaults={
                "name": "Test Basic",
                "region": region,
                "sub_system": EducationSystemProfile.SubSystem.EN,
                "is_active": True,
                "approval_status": EducationSystemProfile.ApprovalStatus.APPROVED,
            },
        )
        # School A has workshop profile, School B has basic only
        TenantSystem.objects.get_or_create(school=self.school_a, system=profile_workshop)
        TenantSystem.objects.get_or_create(school=self.school_b, system=profile_basic)
        self.assertTrue(
            self.school_a.has_feature("workshop_management"),
            "School A has workshop profile so has_feature('workshop_management') must be True",
        )
        self.assertFalse(
            self.school_b.has_feature("workshop_management"),
            "School B has no workshop profile so has_feature('workshop_management') must be False",
        )


class ProvisioningJobTests(TestCase):
    """Provisioning task creates School, membership, academic year, terms."""

    def test_provision_school_sync_creates_membership_and_terms(self):
        school = School.objects.create(
            name="New School",
            slug="new-school",
            subdomain="new-school",
            is_active=False,
        )
        provision_school_sync(str(school.id), contact_email="admin@newschool.com")
        school.refresh_from_db()
        self.assertTrue(school.is_active)
        self.assertEqual(SchoolMembership.objects.filter(school=school).count(), 1)
        self.assertTrue(AcademicYear.objects.filter(school=school).exists())
        self.assertTrue(Term.objects.filter(school=school).exists())

    def test_provision_school_applies_education_profile_defaults(self):
        uganda, _ = RegionConfig.objects.get_or_create(
            code="UGA",
            defaults={
                "name": "Uganda",
                "default_language": "en",
                "timezone": "Africa/Kampala",
                "grading_scale": "0-100",
                "default_currency": "UGX",
                "academic_year_start_month": 2,
                "term_count_per_year": 3,
            },
        )
        school = School.objects.create(
            name="Kampala Academy",
            slug="kampala-academy",
            subdomain="kampala-academy",
            is_active=False,
            default_region=uganda,
            sub_system=School.SubSystem.EN,
        )
        provision_school_sync(str(school.id), contact_email="principal@kampalaacademy.ug")
        school.refresh_from_db()
        term_names = list(
            Term.objects.filter(school=school)
            .order_by("position")
            .values_list("name", flat=True)
        )
        self.assertEqual(term_names[:3], ["Term I", "Term II", "Term III"])
        subjects = set(Subject.objects.filter(school=school).values_list("name", flat=True))
        self.assertIn("Biology", subjects)
        self.assertIn("Mathematics", subjects)
        # Auto-created profile code is {region}-{sub_system}-auto (education_profile_engine._profile_code)
        self.assertEqual((school.settings or {}).get("education_profile_code"), "uga-en-auto")

    def test_provision_school_auto_generates_country_profile_when_missing(self):
        japan, _ = RegionConfig.objects.get_or_create(
            code="JPN",
            defaults={
                "name": "Japan",
                "default_language": "ja",
                "timezone": "Asia/Tokyo",
                "grading_scale": "0-100",
                "default_currency": "JPY",
                "academic_year_start_month": 4,
                "term_count_per_year": 3,
            },
        )
        school = School.objects.create(
            name="Tokyo Academy",
            slug="tokyo-academy",
            subdomain="tokyo-academy",
            is_active=False,
            default_region=japan,
            sub_system=School.SubSystem.EN,
        )

        self.assertFalse(
            EducationSystemProfile.objects.filter(region=japan).exists(),
            "Precondition: no explicit Japan profile should exist before provisioning.",
        )

        provision_school_sync(str(school.id), contact_email="admin@tokyoacademy.jp")
        school.refresh_from_db()
        profile_code = (school.settings or {}).get("education_profile_code")
        self.assertTrue(profile_code)
        self.assertEqual(profile_code, "jpn-en-auto")

        profile = EducationSystemProfile.objects.get(code=profile_code)
        self.assertEqual(profile.region_id, "JPN")
        self.assertTrue((profile.config or {}).get("generated"))

        term_names = list(Term.objects.filter(school=school).order_by("position").values_list("name", flat=True))
        self.assertEqual(term_names[:3], ["Term 1", "Term 2", "Term 3"])

    def test_provision_school_persists_compiled_tenant_config_snapshot(self):
        cmr, _ = RegionConfig.objects.get_or_create(
            code="CMR",
            defaults={
                "name": "Cameroon",
                "default_language": "en",
                "timezone": "Africa/Douala",
                "grading_scale": "0-20",
                "default_currency": "XAF",
                "academic_year_start_month": 9,
                "term_count_per_year": 3,
            },
        )
        school = School.objects.create(
            name="Snapshot School",
            slug="snapshot-school",
            subdomain="snapshot-school",
            is_active=False,
            default_region=cmr,
            sub_system=School.SubSystem.EN,
            settings={"default_language": "fr"},
        )
        provision_school_sync(str(school.id), contact_email="ops@snapshot-school.cm")
        school.refresh_from_db()
        settings = school.settings or {}

        self.assertIn("tenant_compiled_config", settings)
        self.assertIn("tenant_config_metadata", settings)
        self.assertIn("tenant_config_layers", settings)
        self.assertIn("tenant_policy_pack", settings)
        self.assertIn("tenant_config_compiled_at", settings)
        self.assertEqual((settings.get("tenant_policy_pack") or {}).get("code"), "LCA")
        self.assertEqual((settings.get("tenant_compiled_config") or {}).get("default_language"), "fr")


@override_settings(SINGLE_TENANT="true")
class SingleTenantFallbackTests(TestCase):
    """With one school and SINGLE_TENANT=true, app resolves school without subdomain."""

    def setUp(self):
        self.school = School.objects.create(
            name="Only School",
            slug="only",
            subdomain="only",
            is_active=True,
        )

    def test_single_school_resolution(self):
        """Middleware would resolve this school when host has no subdomain; tested via model."""
        from apps.schools.middleware import _get_single_tenant_school
        from apps.schools.models import School
        # Only assert single-tenant when this test is the only one with an active school
        if School.objects.filter(is_active=True).count() != 1:
            self.skipTest("Single-tenant resolution requires exactly one active school in DB (test isolation).")
        single = _get_single_tenant_school()
        self.assertIsNotNone(single)
        self.assertEqual(single.id, self.school.id)


class FeatureFlagTests(TestCase):
    """Disabling a module hides sidebar item and can return 403 for that module URL."""

    def setUp(self):
        self.school = School.objects.create(
            name="Test",
            slug="test",
            subdomain="test",
            is_active=True,
            features={},  # no modules enabled
        )
        self.user = User.objects.create_user(
            username="teacher1",
            email="t@test.com",
            password="testpass123",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(user=self.user, school=self.school, role=User.Role.TEACHER, is_primary=True)

    def test_has_feature_false_when_not_in_features(self):
        self.assertFalse(self.school.has_feature("cahier_de_texte"))

    def test_has_feature_true_when_enabled(self):
        self.school.features = {"cahier_de_texte": True}
        self.school.save()
        self.assertTrue(self.school.has_feature("cahier_de_texte"))


class OfflineSyncPerSchoolTests(TestCase):
    """sync_batch returns 403 when request.school does not have offline_mode module."""

    def test_sync_batch_403_when_school_lacks_offline_mode_module(self):
        from apps.api.mobile_api import MobileDevice
        import uuid

        school = School.objects.create(
            name="No Offline School",
            slug="no-offline",
            subdomain="no-offline",
            is_active=True,
            features={},  # offline_mode not enabled
        )
        user = User.objects.create_user(
            username="offline_test_user",
            password="testpass123",
            is_staff=True,
        )
        SchoolMembership.objects.create(user=user, school=school, role=User.Role.ADMIN, is_primary=True)
        device = MobileDevice.objects.create(
            user=user,
            device_id=uuid.uuid4(),
            device_name="Test",
            platform="WEB",
            app_version="1.0",
        )
        site = get_platform_site_settings_record(create=True)
        site.enable_offline_mode = True
        site.save(update_fields=["enable_offline_mode"])

        client = Client()
        client.force_login(user)
        session = client.session
        session["school_id"] = str(school.id)
        session.save()

        url = reverse("api:offline-sync-sync-batch")
        payload = {
            "device_id": str(device.device_id),
            "changes": [],
        }
        response = client.post(url, payload, content_type="application/json")
        self.assertEqual(response.status_code, 403, response.content)
        try:
            data = response.json()
        except Exception:
            data = {}
        self.assertIn("error", data)
        self.assertIn("Offline", str(data.get("error", "")))


class SuperProvisioningWizardTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.superuser = User.objects.create_superuser(
            username="root",
            email="root@test.com",
            password="testpass123",
        )

    def test_wizard_renders_country_and_city_selectors(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("super:create_school_wizard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="country_code"')
        self.assertContains(response, 'id="city_id"')
        self.assertContains(response, 'id="city_search"')
        self.assertContains(response, "Select country first, then city")

    def test_api_geo_cities_returns_country_matches(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            reverse("super:api_geo_cities"),
            {"country_code": "UGA", "q": "Kamp", "limit": 30},
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload.get("country_code"), "UGA")
        city_names = [str(item.get("city", "")).lower() for item in payload.get("cities", [])]
        self.assertIn("kampala", city_names)

    def test_api_education_profiles_returns_country_pack(self):
        self.client.force_login(self.superuser)
        response = self.client.get(
            reverse("super:api_education_profiles"),
            {"country_code": "JPN", "sub_system": "EN"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload.get("country_code"), "JPN")
        self.assertIn("auto_option", payload)
        profile_codes = [str(item.get("code") or "") for item in payload.get("profiles", [])]
        self.assertIn("jpn-en-auto", profile_codes)

    def test_api_create_school_uses_city_timezone(self):
        self.client.force_login(self.superuser)
        cities = GlobalGeoCatalog.search_cities(country_code="USA", query="New York", limit=10)
        self.assertTrue(cities, "Global city catalog should include New York")
        city = cities[0]

        payload = {
            "name": "Global Academy",
            "slug": "global-academy",
            "subdomain": "global-academy",
            "contact_email": "admin@global.test",
            "country_code": city["country_code"],
            "city_id": str(city["id"]),
            "region_code": city["country_code"],
            "sub_system": "INT",
            "primary_color": "#2d5a27",
            "accent_color": "#f59e0b",
        }
        response = self.client.post(
            reverse("super:api_create_school"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202, response.content)
        school = School.objects.get(slug="global-academy")
        self.assertEqual(school.default_region_id, city["country_code"])
        self.assertEqual(school.timezone, city["timezone"])
        location_settings = (school.settings or {}).get("location") or {}
        self.assertEqual(location_settings.get("country_code"), city["country_code"])
        self.assertEqual(location_settings.get("city"), city["city"])

    def test_api_create_school_persists_explicit_education_profile(self):
        self.client.force_login(self.superuser)
        uganda, _ = RegionConfig.objects.get_or_create(
            code="UGA",
            defaults={
                "name": "Uganda",
                "default_language": "en",
                "timezone": "Africa/Kampala",
                "grading_scale": "0-100",
                "default_currency": "UGX",
                "academic_year_start_month": 2,
                "term_count_per_year": 3,
            },
        )
        profile, _ = EducationSystemProfile.objects.get_or_create(
            code="uga-national-default",
            defaults={
                "name": "Uganda National Default",
                "region": uganda,
                "sub_system": EducationSystemProfile.SubSystem.EN,
                "is_active": True,
                "approval_status": EducationSystemProfile.ApprovalStatus.APPROVED,
            },
        )
        self.assertTrue(profile.is_active)
        cities = GlobalGeoCatalog.search_cities(country_code="UGA", query="Kampala", limit=10)
        self.assertTrue(cities, "Global city catalog should include Kampala")
        city = cities[0]

        payload = {
            "name": "Explicit Profile School",
            "slug": "explicit-profile-school",
            "subdomain": "explicit-profile-school",
            "contact_email": "principal@explicit-profile.test",
            "country_code": city["country_code"],
            "city_id": str(city["id"]),
            "region_code": city["country_code"],
            "sub_system": "EN",
            "education_profile_code": "uga-national-default",
            "primary_color": "#2d5a27",
            "accent_color": "#f59e0b",
        }
        response = self.client.post(
            reverse("super:api_create_school"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202, response.content)
        school = School.objects.get(slug="explicit-profile-school")
        self.assertEqual((school.settings or {}).get("education_profile_code"), "uga-national-default")
        self.assertEqual(
            ((school.settings or {}).get("provisioning") or {}).get("education_profile_mode"),
            "explicit",
        )

    def test_api_create_school_persists_canonical_registry_identity(self):
        self.client.force_login(self.superuser)
        country = CountryRegistry.objects.create(
            code="US",
            alpha3_code="USA",
            name="United States",
            default_language="en",
            default_currency="USD",
            default_timezone="America/New_York",
        )
        subdivision = SubdivisionRegistry.objects.create(
            country=country,
            code="US-VA",
            name="Virginia",
            subdivision_type="state",
        )
        EducationLevelRegistry.objects.create(code="PRIMARY", global_name="Primary", sort_order=10)
        EducationLevelRegistry.objects.create(code="SECONDARY", global_name="Secondary", sort_order=20)
        EducationSystemTypeRegistry.objects.create(code="GENERAL", name="General", sort_order=10)
        EducationSystemTypeRegistry.objects.create(code="STEM", name="STEM", sort_order=20)

        cities = GlobalGeoCatalog.search_cities(country_code="USA", query="New York", limit=10)
        self.assertTrue(cities, "Global city catalog should include New York")
        city = cities[0]
        payload = {
            "name": "Canonical Registry School",
            "slug": "canonical-registry-school",
            "subdomain": "canonical-registry-school",
            "contact_email": "registry-admin@test.com",
            "country_code": "US",
            "city_id": str(city["id"]),
            "region_code": city["country_code"],
            "sub_system": "INT",
            "subdivision_id": subdivision.id,
            "education_level_codes": ["PRIMARY", "SECONDARY"],
            "education_system_type_codes": ["GENERAL", "STEM"],
        }
        response = self.client.post(
            reverse("super:api_create_school"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202, response.content)
        school = School.objects.get(slug="canonical-registry-school")
        self.assertEqual(school.country_code, "US")
        self.assertEqual(school.subdivision_id, subdivision.id)
        self.assertEqual(
            list(school.education_levels.order_by("code").values_list("code", flat=True)),
            ["PRIMARY", "SECONDARY"],
        )
        self.assertEqual(
            list(school.education_system_types.order_by("code").values_list("code", flat=True)),
            ["GENERAL", "STEM"],
        )
        self.assertEqual(((school.settings or {}).get("location") or {}).get("country_code_alpha2"), "US")

    def test_api_create_school_rejects_non_approved_explicit_profile(self):
        self.client.force_login(self.superuser)
        uganda, _ = RegionConfig.objects.get_or_create(
            code="UGA",
            defaults={
                "name": "Uganda",
                "default_language": "en",
                "timezone": "Africa/Kampala",
                "grading_scale": "0-100",
                "default_currency": "UGX",
                "academic_year_start_month": 2,
                "term_count_per_year": 3,
            },
        )
        draft_profile = EducationSystemProfile.objects.create(
            code="uga-explicit-draft-api",
            name="Uganda Draft API Pack",
            region=uganda,
            sub_system=EducationSystemProfile.SubSystem.EN,
            approval_status=EducationSystemProfile.ApprovalStatus.DRAFT,
            is_active=True,
        )
        cities = GlobalGeoCatalog.search_cities(country_code="UGA", query="Kampala", limit=10)
        self.assertTrue(cities, "Global city catalog should include Kampala")
        city = cities[0]

        payload = {
            "name": "Draft Profile API School",
            "slug": "draft-profile-api-school",
            "subdomain": "draft-profile-api-school",
            "contact_email": "principal@draft-profile-api.test",
            "country_code": city["country_code"],
            "city_id": str(city["id"]),
            "region_code": city["country_code"],
            "sub_system": "EN",
            "education_profile_code": draft_profile.code,
            "primary_color": "#2d5a27",
            "accent_color": "#f59e0b",
        }
        response = self.client.post(
            reverse("super:api_create_school"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        data = response.json()
        self.assertIn("errors", data)
        self.assertTrue(any("education_profile_code" in str(err) for err in data.get("errors", [])))

    def test_api_create_school_records_provisioning_events_and_timeline_url(self):
        self.client.force_login(self.superuser)
        city = None
        for query in ("Boston", "New York", "Los Angeles", "Chicago"):
            cities = GlobalGeoCatalog.search_cities(country_code="USA", query=query, limit=10)
            if cities:
                city = cities[0]
                break
        self.assertIsNotNone(city, "Global city catalog should include at least one major US city")

        payload = {
            "name": "Timeline School",
            "slug": "timeline-school",
            "subdomain": "timeline-school",
            "contact_email": "timeline-admin@test.com",
            "country_code": city["country_code"],
            "city_id": str(city["id"]),
            "region_code": city["country_code"],
            "sub_system": "INT",
            "primary_color": "#2d5a27",
            "accent_color": "#f59e0b",
        }
        response = self.client.post(
            reverse("super:api_create_school"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202, response.content)
        body = response.json()
        self.assertIn("timeline_url", body)
        school = School.objects.get(slug="timeline-school")
        event_types = set(
            SchoolProvisioningEvent.objects.filter(school=school).values_list("event_type", flat=True)
        )
        self.assertIn("REQUEST_RECEIVED", event_types)
        self.assertIn("QUEUED", event_types)
        self.assertTrue({"STARTED", "COMPLETED"} & event_types)

    def test_api_school_timeline_returns_ordered_events(self):
        self.client.force_login(self.superuser)
        school = School.objects.create(
            name="Timeline Endpoint School",
            slug="timeline-endpoint-school",
            subdomain="timeline-endpoint-school",
            is_active=False,
        )
        SchoolProvisioningEvent.log_event(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.REQUEST_RECEIVED,
            status=SchoolProvisioningEvent.Status.INFO,
            message="Request accepted",
        )
        SchoolProvisioningEvent.log_event(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.QUEUED,
            status=SchoolProvisioningEvent.Status.INFO,
            message="Queued",
        )
        response = self.client.get(reverse("super:api_school_timeline", args=[school.id]))
        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload.get("school_id"), str(school.id))
        events = payload.get("events") or []
        self.assertGreaterEqual(len(events), 2)
        self.assertEqual(events[0].get("event_type"), SchoolProvisioningEvent.EventType.QUEUED)
        self.assertEqual(events[1].get("event_type"), SchoolProvisioningEvent.EventType.REQUEST_RECEIVED)


class CustomDomainVerificationCommandTests(TestCase):
    def test_verify_custom_domains_logs_verification_event(self):
        school = School.objects.create(
            name="Domain School",
            slug="domain-school",
            subdomain="domain-school",
            custom_domain="portal.domainschool.edu",
            custom_domain_verified=False,
            is_active=True,
        )

        with patch("apps.schools.management.commands.verify_custom_domains.socket.getaddrinfo", return_value=[("ok",)]):
            call_command("verify_custom_domains")

        school.refresh_from_db()
        self.assertTrue(school.custom_domain_verified)
        custom_domain_payload = (school.settings or {}).get("custom_domain") or {}
        self.assertEqual(custom_domain_payload.get("status"), "verified")
        self.assertTrue(custom_domain_payload.get("verified"))
        self.assertTrue(
            SchoolProvisioningEvent.objects.filter(
                school=school,
                event_type=SchoolProvisioningEvent.EventType.DOMAIN_VERIFIED,
            ).exists()
        )
