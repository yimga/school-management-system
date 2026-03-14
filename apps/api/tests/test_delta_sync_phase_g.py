"""
Phase G integration tests: Delta sync conflict, offline queue semantics, tenant isolation.

1) Sync conflict: two clients edit same record; server returns conflict and does not overwrite.
2) Offline queue: when delta returns 200 for an item, client can clear that item from queue (removed_ids).
3) Tenant isolation: cache key must include tenant_id; conflicts are scoped by school.
"""

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department
from apps.api.sync_delta_api import DeltaSyncAPI
from apps.people.models import StudentProfile
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.schools.models import School
from apps.siteconfig.models import SyncConflict


class DeltaSyncConflictTestCase(TestCase):
    """Server returns conflict and does not overwrite when server.updated_at > client_updated_at."""

    def setUp(self):
        self.school = School.objects.create(
            name="Conflict Test School",
            slug="conflict-test",
            subdomain="conflict-test",
        )
        self.user = User.objects.create_superuser(
            username="delta_user",
            password="testpass123",
            email="delta@test.com",
        )
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)

        year = AcademicYear.objects.create(
            name="2024-2025",
            starts_on="2024-01-01",
            ends_on="2024-12-31",
            school=self.school,
        )
        dept = Department.objects.create(name="Conflict Test Dept", code="CTD")
        self.classroom = Classroom.objects.create(
            academic_year=year,
            department=dept,
            name="Form 1A",
            code="F1A",
            school=self.school,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Delta",
            last_name="Student",
            date_of_birth="2012-01-01",
        )

        site = get_platform_site_settings_record(create=True)
        site.enable_offline_mode = True
        site.save(update_fields=["enable_offline_mode"])

    def test_conflict_returns_409_and_does_not_overwrite(self):
        """When client sends an older updated_at than server, server returns 409 and does not apply changes."""
        self.student.first_name = "ServerName"
        self.student.save(update_fields=["first_name", "updated_at"])
        self.student.refresh_from_db()
        server_updated_at = self.student.updated_at
        if timezone.is_naive(server_updated_at):
            server_updated_at = timezone.make_aware(server_updated_at, timezone.get_current_timezone())
        old_client_time = server_updated_at - timezone.timedelta(minutes=5)

        from apps.api.sync_services import apply_changes
        out = apply_changes(
            str(self.school.id),
            self.user,
            [
                {
                    "entity_type": "student",
                    "id": self.student.pk,
                    "changes": {"first_name": "ClientName"},
                    "updated_at": old_client_time.isoformat(),
                },
            ],
            persist_conflicts=True,
        )
        self.student.refresh_from_db()
        # Server must not be overwritten when client sent older updated_at (conflict path)
        self.assertEqual(self.student.first_name, "ServerName")
        self.assertEqual(out["success_count"], 0, "Should not apply when conflict")
        self.assertEqual(len(out["conflicts"]), 1, f"Expected 1 conflict, got results={out['results']}")
        self.assertEqual(SyncConflict.objects.filter(school=self.school).count(), 1)
        sc = SyncConflict.objects.get(school=self.school)
        self.assertEqual(sc.entity_type, "student")
        self.assertEqual(sc.entity_id, self.student.pk)
        self.assertEqual(sc.client_data.get("first_name"), "ClientName")
        self.assertEqual(sc.server_data.get("first_name"), "ServerName")


class DeltaSyncSuccessClearQueueTestCase(TestCase):
    """When delta returns 200 for items, client can clear those from queue (removed_ids)."""

    def setUp(self):
        self.school = School.objects.create(
            name="Queue Test School",
            slug="queue-test",
            subdomain="queue-test",
        )
        self.user = User.objects.create_user(
            username="queue_user",
            password="testpass123",
            is_staff=True,
        )
        year = AcademicYear.objects.create(
            name="2024-2025",
            starts_on="2024-01-01",
            ends_on="2024-12-31",
            school=self.school,
        )
        dept = Department.objects.create(name="Queue Dept", code="QTD")
        self.classroom = Classroom.objects.create(
            academic_year=year,
            department=dept,
            name="1A",
            code="1A",
            school=self.school,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="A",
            last_name="B",
            date_of_birth="2012-01-01",
        )
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)
        self.request_factory = APIRequestFactory()
        site = get_platform_site_settings_record(create=True)
        site.enable_offline_mode = True
        site.save(update_fields=["enable_offline_mode"])

    def test_success_returns_200_and_removed_ids(self):
        """Delta apply succeeds; response includes success_count and removed_ids so client clears queue after 200 OK."""
        request = self.request_factory.post(
            "/api/offline/delta/",
            {
                "items": [
                    {
                        "entity_type": "student",
                        "id": self.student.pk,
                        "changes": {"first_name": "Updated"},
                        "updated_at": (timezone.now() + timezone.timedelta(minutes=10)).isoformat(),
                        "client_item_id": "queue-item-1",
                    },
                ],
            },
            format="json",
        )
        request.school = self.school
        force_authenticate(request, user=self.user)
        response = DeltaSyncAPI.as_view()(request)
        self.assertEqual(response.status_code, 200)
        out = response.data
        self.assertEqual(out["success_count"], 1)
        self.assertEqual(len(out["conflicts"]), 0)
        self.assertEqual(out["removed_ids"], ["queue-item-1"])
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "Updated")


class DeltaSyncTenantIsolationTestCase(TestCase):
    """Conflicts are scoped by school; cache key must include tenant_id (documented)."""

    def setUp(self):
        self.school_a = School.objects.create(name="School A", slug="school-a", subdomain="school-a")
        self.school_b = School.objects.create(name="School B", slug="school-b", subdomain="school-b")
        self.user = User.objects.create_superuser(username="iso_user", password="testpass123", email="i@test.com")
        for i, school in enumerate((self.school_a, self.school_b)):
            year = AcademicYear.objects.create(
                name="2024-2025",
                starts_on="2024-01-01",
                ends_on="2024-12-31",
                school=school,
            )
            dept = Department.objects.create(name=f"Iso Dept {i}", code=f"ISO{i}")
            Classroom.objects.create(
                academic_year=year,
                department=dept,
                name="1A",
                code=f"1A-{i}",
                school=school,
            )
        self.student_a = StudentProfile.objects.create(
            school=self.school_a,
            first_name="A",
            last_name="B",
            date_of_birth="2012-01-01",
        )
        self.student_b = StudentProfile.objects.create(
            school=self.school_b,
            first_name="X",
            last_name="Y",
            date_of_birth="2012-01-01",
        )
        site = get_platform_site_settings_record(create=True)
        site.enable_offline_mode = True
        site.save(update_fields=["enable_offline_mode"])

    def test_conflict_scoped_to_school(self):
        """SyncConflict records are created with school_id; no cross-tenant data."""
        from apps.api.sync_services import apply_changes
        # Create conflict for school_a
        self.student_a.save(update_fields=["updated_at"])
        server_dt = self.student_a.updated_at
        old_dt = server_dt - timezone.timedelta(minutes=5)
        out_a = apply_changes(
            str(self.school_a.id),
            self.user,
            [
                {
                    "entity_type": "student",
                    "id": self.student_a.pk,
                    "changes": {"first_name": "ClientA"},
                    "updated_at": old_dt.isoformat(),
                },
            ],
            persist_conflicts=True,
        )
        self.assertEqual(len(out_a["conflicts"]), 1)
        self.assertEqual(SyncConflict.objects.filter(school=self.school_a).count(), 1)
        self.assertEqual(SyncConflict.objects.filter(school=self.school_b).count(), 0)
        # Frontend MUST use tenant-scoped cache key (e.g. sync_queue_${school_id}) so no cross-tenant data
        # This test asserts backend stores conflict per school only.
        sc = SyncConflict.objects.get(school=self.school_a)
        self.assertEqual(sc.school_id, self.school_a.id)
