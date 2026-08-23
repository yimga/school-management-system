"""Regression: a single-tenant DR restore must not rewrite platform-wide users.

``accounts.User`` is shared/public and its restore natural key is the GLOBAL
``username``, so restoring school A used to issue a full-column UPDATE over any
live row that merely collided on username — reverting the password hash of a
teacher who had moved to school B, and re-promoting anyone demoted since the
snapshot was captured.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.academics.models import Department
from apps.lifecycle.tenant_dr_snapshot import (
    capture_daily_snapshot,
    restore_from_snapshot,
)
from apps.people.models import TeacherProfile
from apps.schools.models import School, SchoolMembership

User = get_user_model()


@override_settings(SECRET_KEY="test-dr-user-isolation-signing-key")
class DrSnapshotUserIsolationTests(TestCase):
    def setUp(self):
        tag = uuid.uuid4().hex[:8]
        self.source = School.objects.create(
            name="DR Source", slug=f"dr-src-{tag}", subdomain=f"dr-src-{tag}"
        )
        self.dept = Department.objects.create(
            school=self.source, name="Sciences", code=f"SCI-{tag}"
        )
        self.user = User.objects.create_user(
            username=f"moving-teacher-{tag}",
            email="before@example.test",
            password="password-at-capture-time",
            role=User.Role.TEACHER,
        )
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        TeacherProfile.objects.create(
            school=self.source,
            user=self.user,
            staff_id=f"STAFF-{tag}",
            position_title="Physics",
            department=self.dept,
        )
        self.membership = SchoolMembership.objects.create(
            user=self.user, school=self.source, role=User.Role.TEACHER
        )
        self.meta = capture_daily_snapshot(self.source)
        self.captured_hash = self.user.password

    def _restore_into(self, target):
        return restore_from_snapshot(
            Path(self.meta["primary_uri"]),
            school_id=str(self.source.pk),
            expected_sig=self.meta["signature_hex"],
            target_school=target,
        )

    def test_restore_does_not_touch_a_username_collision_at_another_school(self):
        # The teacher leaves for another school, keeps the username, changes
        # their password and is demoted.
        # ``TeacherProfile.user`` is a OneToOne, so the source profile must be
        # gone before the snapshot can materialise one under the target — which
        # is exactly the state a fresh-instance DR restores into.
        TeacherProfile.objects.filter(school=self.source).delete()
        self.membership.delete()
        self.user.set_password("password-after-the-move")
        self.user.is_superuser = False
        self.user.email = "after@example.test"
        self.user.save()
        moved_hash = self.user.password

        tag = uuid.uuid4().hex[:8]
        target = School.objects.create(
            name="DR Target", slug=f"dr-tgt-{tag}", subdomain=f"dr-tgt-{tag}"
        )
        result = self._restore_into(target)

        # Vacuity guard: the snapshot really did carry this user, so "unchanged"
        # is a decision the restore made, not an empty table.
        snapshot_usernames = {
            row["fields"]["username"] for row in result["tables"]["accounts.User"]
        }
        self.assertIn(self.user.username, snapshot_usernames)

        self.user.refresh_from_db()
        self.assertEqual(self.user.password, moved_hash)
        self.assertNotEqual(self.user.password, self.captured_hash)
        self.assertFalse(self.user.is_superuser)
        self.assertEqual(self.user.email, "after@example.test")

        report = result["restored"]["tables"]["accounts.User"]
        self.assertEqual(report["updated"], 0)
        self.assertEqual(report["skipped"], 1)

        # The skip must not break the restore: the tenant's own teacher row is
        # still materialised and still points at the right identity.
        restored_teacher = TeacherProfile.objects.get(school=target)
        self.assertEqual(restored_teacher.user_id, self.user.pk)

    def test_member_row_updates_but_platform_privilege_is_never_restored(self):
        self.user.is_superuser = False
        self.user.email = "changed@example.test"
        self.user.save(update_fields=["is_superuser", "email"])

        result = self._restore_into(self.source)

        self.user.refresh_from_db()
        # The row WAS updated — the snapshot's email came back...
        self.assertEqual(self.user.email, "before@example.test")
        self.assertEqual(result["restored"]["tables"]["accounts.User"]["updated"], 1)
        # ...but a tenant restore may never re-promote a demoted account.
        self.assertFalse(self.user.is_superuser)
