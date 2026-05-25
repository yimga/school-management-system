"""ReBAC tuples + offline IAM snapshot (batch 1507)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.iam_snapshot import (
    build_permission_snapshot,
    sign_snapshot,
    snapshot_not_expired,
    verify_snapshot_signature,
)
from apps.accounts.models_rebac import OfflineAccessIntent, RelationshipTuple
from apps.accounts.rebac import (
    OBJECT_PERMISSION,
    OBJECT_SCHOOL,
    REL_CAN,
    REL_MEMBER,
    SUBJECT_USER,
    check,
    check_permission_token,
    write_tuple,
)
from apps.accounts.rebac_intents import apply_offline_access_intent, enqueue_request_access
from apps.accounts.rebac_sync import sync_membership_tuples
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class RebacTupleTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="ReBAC School",
            slug="rebac-school",
            subdomain="rebac",
            country_code="US",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="rebac_user",
            password="Test1234!",
            role=User.Role.TEACHER,
        )

    def test_membership_emits_member_tuple(self):
        m = SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.TEACHER,
        )
        sync_membership_tuples(m)
        self.assertTrue(
            check(
                self.user,
                REL_MEMBER,
                OBJECT_SCHOOL,
                str(self.school.pk),
                school=self.school,
            ),
        )

    def test_write_can_permission_tuple(self):
        write_tuple(
            school=self.school,
            subject_type=SUBJECT_USER,
            subject_id=str(self.user.pk),
            relation=REL_CAN,
            object_type=OBJECT_PERMISSION,
            object_id="reports.view",
            source=RelationshipTuple.Source.BACKFILL,
            source_key="test:1",
        )
        self.assertTrue(
            check_permission_token(self.user, "reports.view", school=self.school),
        )

    def test_superuser_check_always_true(self):
        admin = User.objects.create_superuser(
            username="rebac_admin",
            password="Test1234!",
            email="admin@example.com",
        )
        self.assertTrue(
            check(admin, REL_MEMBER, OBJECT_SCHOOL, "999", school=self.school),
        )


class IamSnapshotTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Snap School",
            slug="snap-school",
            subdomain="snap",
            country_code="US",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="snap_user",
            password="Test1234!",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.ADMIN,
        )

    def test_snapshot_signed_and_valid(self):
        body = build_permission_snapshot(self.user, school=self.school)
        signed = sign_snapshot(dict(body))
        self.assertIn("signature", signed)
        sig = signed.pop("signature")
        self.assertTrue(verify_snapshot_signature({**signed, "signature": sig}))
        self.assertTrue(snapshot_not_expired(signed))
        self.assertTrue(signed.get("read_only"))
        self.assertFalse(signed.get("offline_admin_grants"))


class OfflineIamIntentTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Intent School",
            slug="intent-school",
            subdomain="intent",
            country_code="US",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="intent_user",
            password="Test1234!",
            role=User.Role.TEACHER,
        )

    def test_request_access_never_grants_admin(self):
        intent = enqueue_request_access(
            user=self.user,
            school=self.school,
            permission_code="settings.manage",
            reason="offline request",
        )
        ok, note = apply_offline_access_intent(intent)
        self.assertTrue(ok)
        intent.refresh_from_db()
        self.assertEqual(intent.status, OfflineAccessIntent.Status.REJECTED)
        self.assertEqual(note, "forbidden_capability")

    def test_request_access_logs_benign_code(self):
        intent = enqueue_request_access(
            user=self.user,
            school=self.school,
            permission_code="student.note",
        )
        ok, _note = apply_offline_access_intent(intent)
        self.assertTrue(ok)
        intent.refresh_from_db()
        self.assertEqual(intent.status, OfflineAccessIntent.Status.APPLIED)


class PermissionSnapshotApiTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="API School",
            slug="api-school",
            subdomain="apischool",
            country_code="US",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="api_snap",
            password="Test1234!",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.create(
            user=self.user,
            school=self.school,
            role=User.Role.TEACHER,
        )

    def test_snapshot_api_returns_signed_payload(self):
        from apps.api.iam_offline_api import PermissionSnapshotAPI

        request = self.factory.get("/api/offline/permission_snapshot/")
        request.user = self.user
        request.school = self.school
        response = PermissionSnapshotAPI.as_view()(request)
        self.assertEqual(response.status_code, 200)
        snap = response.data["snapshot"]
        self.assertIn("signature", snap)
        self.assertEqual(snap["school_id"], str(self.school.pk))
