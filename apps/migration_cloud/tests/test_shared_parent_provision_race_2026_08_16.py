"""Parallel-wave provisioning of a shared parent must not spuriously quarantine.

Feature ④ (Migration Cloud → 100% infallible), finding #8.

Artifacts in one apply wave run in parallel on SEPARATE DB connections. Two threads
can both miss the "does this parent exist?" filter and both try to create the same
shared parent (a Department/AcademicYear/Classroom by (school, name); a staff/guardian
User by email). The loser hits an IntegrityError and its child row was quarantined —
even though the parent now exists and the row would otherwise land.

Both provisioning helpers now re-resolve the winner on IntegrityError instead of
failing — but ONLY by the entity's identity (school+name for named parents; email for
users), so a mere username-derivation collision between two DIFFERENT people is never
silently merged (it re-raises and quarantines honestly).

Before the fix, the race tests raise IntegrityError instead of returning the winner.
"""
from __future__ import annotations

import contextlib
from unittest import mock

from django.db import IntegrityError
from django.test import TestCase

from apps.accounts.models import User
from apps.migration_cloud.landers import _helpers
from apps.migration_cloud.landers._helpers import (
    get_or_create_named,
    resolve_or_provision_user,
)
from apps.schools.models import School

_NULL_SAVEPOINT = lambda: contextlib.nullcontext()  # noqa: E731 — let the winner insert survive the raise


class ResolveOrProvisionUserRaceTests(TestCase):
    def test_reresolves_to_winner_on_email_race(self):
        def _winner_then_raise(**kwargs):
            # A concurrent wave-thread provisioned the SAME person first, then our
            # create collides on the shared email-derived username.
            User.objects.create(username="winner", email="teacher@x.com")
            raise IntegrityError("duplicate username")

        with mock.patch.object(_helpers, "row_savepoint", _NULL_SAVEPOINT), \
                mock.patch.object(User.objects, "create_user", side_effect=_winner_then_raise):
            user, reason = resolve_or_provision_user(
                User=User, username_hint="", email="teacher@x.com",
                first_name="T", last_name="Eacher", role="", dry_run=False,
            )

        self.assertEqual(reason, "")
        self.assertIsNotNone(user)
        self.assertEqual(user.email, "teacher@x.com")
        self.assertEqual(user.username, "winner")  # bound to the winner, NOT quarantined

    def test_reraises_when_no_email_match(self):
        # A username collision with NO matching email = a DIFFERENT person. Merging
        # would corrupt identity, so this must re-raise (honest quarantine).
        def _just_raise(**kwargs):
            raise IntegrityError("username collision, different person")

        with mock.patch.object(_helpers, "row_savepoint", _NULL_SAVEPOINT), \
                mock.patch.object(User.objects, "create_user", side_effect=_just_raise):
            with self.assertRaises(IntegrityError):
                resolve_or_provision_user(
                    User=User, username_hint="", email="lonely@x.com",
                    first_name="L", last_name="One", role="", dry_run=False,
                )


class GetOrCreateNamedRaceTests(TestCase):
    def _school(self):
        return School.objects.create(
            name="Race", slug="race", subdomain="race", is_active=True, country_code="CM",
        )

    def test_reresolves_to_winner_on_shared_parent_race(self):
        from apps.academics.models import Department

        school = self._school()

        def _winner_then_raise(**kwargs):
            # Concurrent wave-thread already created this exact (school, name).
            Department.objects.bulk_create([Department(school=school, name="Science", code="SCI")])
            raise IntegrityError("duplicate (school, name)")

        with mock.patch.object(_helpers, "row_savepoint", _NULL_SAVEPOINT), \
                mock.patch.object(Department.objects, "create", side_effect=_winner_then_raise):
            obj, created = get_or_create_named(
                model=Department, school=school, name="Science",
                create_kwargs=lambda: {"code": "SCI-2"},
            )

        self.assertFalse(created)             # re-resolved, not newly created
        self.assertEqual(obj.name, "Science")
        self.assertEqual(obj.code, "SCI")     # the WINNER's row, not ours

    def test_normal_get_or_create_still_reuses(self):
        from apps.academics.models import Department

        school = self._school()
        a, created_a = get_or_create_named(
            model=Department, school=school, name="Arts", create_kwargs=lambda: {"code": "ART"},
        )
        b, created_b = get_or_create_named(
            model=Department, school=school, name="Arts", create_kwargs=lambda: {"code": "ART2"},
        )
        self.assertTrue(created_a)
        self.assertFalse(created_b)           # reused, never duplicated
        self.assertEqual(a.pk, b.pk)
