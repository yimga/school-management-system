"""A failing DSL alert must not discard the disclosure it was announcing.

``_dispatch_dsl_alert`` catches ``Exception`` under the comment "alert must never
unwind submit", and ``submit_concern_for_school`` is ``@transaction.atomic``. That
pairing does NOT do what it says. ``dispatch_event`` writes a Notification row for
the in-app bell, and when a database error is raised inside an atomic block Django
sets ``connection.needs_rollback``. Catching the exception does not clear that
flag, so when the outer block exits it rolls the whole transaction back -- the
concern included.

The result is the worst possible failure for this module: a child-protection
disclosure is submitted, the reporter is told it was recorded, the alert fails,
and the concern is silently gone. The same shape is already documented elsewhere
in this codebase ("decide() swallows a database error inside its own
@transaction.atomic, poisoning the connection").

The fix is a savepoint around the alert, so a failure there rolls back only the
alert -- rolling back to a savepoint is what CLEARS ``needs_rollback``.

HOW THIS IS TESTED, HONESTLY. The poisoning is a PostgreSQL behaviour; SQLite,
which this suite runs on, does not abort a transaction on a failed statement, so
simply raising a DatabaseError here proves nothing (it passes on an unfixed tree).
The tests therefore reproduce the MECHANISM directly: the failing dispatch calls
``transaction.set_rollback(True)`` -- exactly the flag Django sets for you when a
statement fails inside an atomic block -- and then raises. That is DB-agnostic and
fails before the fix, passes after.
"""

from __future__ import annotations

import uuid
from unittest import mock

from django.db import DatabaseError, transaction
from django.test import TestCase

from apps.accounts.models import User
from apps.safeguarding.concern_kernel import SUBMITTED
from apps.safeguarding.services import find_concern, submit_concern_for_school
from apps.schools.models import School, SchoolMembership


class AlertFailureNeverLosesConcernTests(TestCase):
    def setUp(self):
        slug = f"sgalert-{uuid.uuid4().hex[:8]}"
        self.school = School.objects.create(
            name="Alert School", slug=slug, subdomain=slug
        )
        self.reporter = User.objects.create_user(
            username=f"rep_{slug}", password="x"
        )
        self.admin = User.objects.create_user(username=f"adm_{slug}", password="x")
        self.admin.role = "ADMIN"
        self.admin.save(update_fields=["role"])
        SchoolMembership.objects.create(
            user=self.reporter, school=self.school, role="TEACHER"
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role="ADMIN"
        )

    def _submit(self):
        return submit_concern_for_school(
            school=self.school,
            reporter_user_id=self.reporter.pk,
            category_key="physical_abuse",
            narrative="Disclosed after training.",
        )

    def test_the_happy_path_persists(self):
        # Calibration: if submit never persisted anything, the assertion below
        # would pass for the wrong reason.
        entry = self._submit()
        self.school.refresh_from_db()
        self.assertIsNotNone(find_concern(self.school, entry.concern_id))
        self.assertEqual(entry.stage, SUBMITTED)

    def test_a_database_error_in_the_alert_does_not_discard_the_concern(self):
        def _fails_like_a_real_db_error(*args, **kwargs):
            # What Django does for you when a statement fails inside atomic().
            transaction.set_rollback(True)
            raise DatabaseError("bell table is gone")

        with mock.patch(
            "apps.communication.dispatch.dispatch_event",
            side_effect=_fails_like_a_real_db_error,
        ):
            entry = self._submit()

        self.school.refresh_from_db()
        self.assertIsNotNone(
            find_concern(self.school, entry.concern_id),
            "the alert failed, so the disclosure was rolled back with it",
        )

    def test_a_plain_exception_in_the_alert_does_not_discard_it_either(self):
        with mock.patch(
            "apps.communication.dispatch.dispatch_event",
            side_effect=RuntimeError("sms gateway down"),
        ):
            entry = self._submit()

        self.school.refresh_from_db()
        self.assertIsNotNone(find_concern(self.school, entry.concern_id))
