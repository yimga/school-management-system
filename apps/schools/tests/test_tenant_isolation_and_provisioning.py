"""
Tests for tenant isolation, provisioning job, single-tenant fallback, and feature-flag enforcement (Option B+C).
"""
from django.test import TestCase, Client, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership
from apps.schools.tasks import provision_school_sync
from apps.people.models import StudentProfile
from apps.academics.models import AcademicYear, Term


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
        from apps.siteconfig.models import SiteSettings
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
        site = SiteSettings.get_solo()
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
