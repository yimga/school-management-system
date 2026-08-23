"""The provisioning race-recovery must not re-open the cross-tenant email hole.

``resolve_or_provision_user`` gates its email rung with
``user_is_linkable_to_school``: a match belonging only to ANOTHER school holds
the row instead of binding a foreign account into this import. But the rung is
not the only place the function resolves by email. When two wave-threads race to
provision the same person, ``create_user`` loses on the unique ``username`` and
the ``except IntegrityError`` re-resolves **by email** so the child row binds to
the winner rather than being spuriously quarantined.

That recovery lookup was unscoped. It is reached exactly when the email rung saw
nothing — i.e. when the winner committed in the window between the rung and the
insert — so the account it hands back has never been checked against this
school, and a concurrent import running for a DIFFERENT tenant is precisely the
writer that wins that race. The gate closed the front door and left this one
open.

The race is forced deterministically rather than threaded: ``row_savepoint`` is
replaced with a context manager that creates the winning row on entry, which is
the same window a real concurrent commit lands in.
"""

from __future__ import annotations

import contextlib
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase

from apps.migration_cloud.landers import _helpers
from apps.migration_cloud.landers._helpers import resolve_or_provision_user
from apps.schools.models import School, SchoolMembership

User = get_user_model()

RACED_EMAIL = "registrar@schoolb.example"
#: ``_free_username`` derives this from the email stem, so the winner created
#: inside the race window collides with it and forces the IntegrityError.
RACED_USERNAME = "registrar"


class _RaceBase(TestCase):
    def setUp(self):
        self.school_a = School.objects.create(
            name="Race Tenant A", slug="race-tenant-a", subdomain="race-tenant-a"
        )
        self.school_b = School.objects.create(
            name="Race Tenant B", slug="race-tenant-b", subdomain="race-tenant-b"
        )

    def _winner_savepoint(self, *, member_of):
        """Stand in for ``row_savepoint``: land the race winner on entry, then
        open the real savepoint around the losing ``create_user``.

        The winner is written OUTSIDE that savepoint on purpose — a real winner
        is another connection's committed row and must survive the loser's
        rollback. The savepoint itself is kept because it is what lets the loser
        keep querying after the IntegrityError at all.
        """

        @contextlib.contextmanager
        def _cm():
            winner = User.objects.create_user(
                username=RACED_USERNAME, email=RACED_EMAIL,
                first_name="Rita", last_name="Registrar",
            )
            if member_of is not None:
                SchoolMembership.objects.create(
                    user=winner, school=member_of, role="ADMIN", is_primary=True
                )
            self.winner = winner
            with transaction.atomic():
                yield

        return _cm

    def _resolve(self, *, member_of):
        # Vacuity guard: the email rung must MISS, or the recovery path under
        # test is never reached and this test would pass on the front door's fix.
        self.assertFalse(
            User.objects.filter(email__iexact=RACED_EMAIL).exists(),
            "the winner must not exist yet — the rung would short-circuit",
        )
        with mock.patch.object(
            _helpers, "row_savepoint", self._winner_savepoint(member_of=member_of)
        ):
            user, reason = resolve_or_provision_user(
                User=User,
                username_hint="",
                email=RACED_EMAIL,
                first_name="Rita",
                last_name="Registrar",
                role="TEACHER",
                dry_run=False,
                school=self.school_a,
            )
        # Vacuity guard: the race really happened — the winner landed and the
        # loser's own create really did fail, so exactly one row carries it.
        self.assertEqual(User.objects.filter(username=RACED_USERNAME).count(), 1)
        self.assertEqual(User.objects.filter(email__iexact=RACED_EMAIL).count(), 1)
        return user, reason


class ProvisionRaceForeignEmailTests(_RaceBase):
    def test_a_foreign_race_winner_is_not_handed_back(self):
        user, reason = self._resolve(member_of=self.school_b)
        self.assertIsNone(
            user,
            "the recovery bound a user who belongs only to another school",
        )
        self.assertIn("another school", reason)
        # And nothing was silently granted in the importing school.
        self.assertFalse(
            SchoolMembership.objects.filter(
                user=self.winner, school=self.school_a
            ).exists()
        )

    def test_a_same_school_race_winner_is_still_recovered(self):
        # The recovery exists so a lost race binds the child row to the winner
        # instead of quarantining it. That must keep working.
        user, reason = self._resolve(member_of=self.school_a)
        self.assertEqual(user, self.winner)
        self.assertEqual(reason, "")

    def test_an_unclaimed_race_winner_is_still_recovered(self):
        # A freshly provisioned account with no membership yet is the ordinary
        # case for two threads provisioning the same new person.
        user, reason = self._resolve(member_of=None)
        self.assertEqual(user, self.winner)
        self.assertEqual(reason, "")
