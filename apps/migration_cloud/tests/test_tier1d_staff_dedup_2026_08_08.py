"""Tier 1d A-Z upgrade wave (2026-08-08): exact-staff_id staff dedup.

Completes the "no duplicate people" set (students → guardians → staff). A staff
member's identity is a platform ``User`` linked from ``TeacherProfile`` via a
OneToOne, and the staff upsert is keyed on that ``user``. ``TeacherProfile.staff_id``
is NOT unique, so the SAME staffer re-imported under a different / absent email
(``resolve_or_provision_user`` matches only exact username / email, then
PROVISIONS) was re-provisioned as a DUPLICATE account + a second TeacherProfile
carrying the same staff_id.

This adds an exact employee-number rung that runs FIRST: an existing
TeacherProfile in the same school carrying this staff_id is the same person, so
its user is reused and the upsert updates in place. ``staff_id`` is the source
SIS's stable identity key (unlike a shared household phone), so an exact single
match is a safe auto-merge; >1 match (legacy duplicate data) is ambiguous and is
NOT guessed.

Each test fails against the pre-Tier-1d lander (which provisions a duplicate
instead of linking by staff_id).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.staff_lander import StaffLander
from apps.migration_cloud.models import MigrationBundle
from apps.people.models import TeacherProfile
from apps.schools.models import School

User = get_user_model()


def _ctx(school, dry_run=False, bundle_id=None) -> LanderContext:
    return LanderContext(
        school=school, schema_name="", bundle_id=bundle_id, artifact_id=None,
        dry_run=dry_run,
    )


class StaffDedupTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Staff Dedup Co", slug="staff-dedup-co", subdomain="staff-dedup-co"
        )

    def _row(self, first="Jane", last="Doe", staff_ext="EMP-1", **over):
        row = {
            "staff_external_id": staff_ext,
            "first_name": first,
            "last_name": last,
            "role": "Teacher",
        }
        row.update(over)
        return row

    def _land(self, *rows, school=None, **ctx_over):
        return StaffLander().land(
            canonical_rows=iter(rows),
            ctx=_ctx(school or self.school, **ctx_over),
        )

    def _staff_users(self, staff_id="EMP-1", school=None):
        return set(
            TeacherProfile.objects.filter(
                staff_id=staff_id, school=school or self.school
            ).values_list("user_id", flat=True)
        )

    def test_reimport_different_email_links_by_staff_id_not_duplicate(self):
        # First import provisions the account + a profile keyed on staff_id.
        a = self._land(self._row(email="jane@ex.com"))
        self.assertEqual(a.quarantined, 0, a.errors)
        first_user = TeacherProfile.objects.get(staff_id="EMP-1").user
        # SAME staff_id, DIFFERENT email — must reuse the account, not provision.
        b = self._land(self._row(email="jane.doe@newmail.com"))
        self.assertEqual(b.quarantined, 0, b.errors)
        self.assertEqual(TeacherProfile.objects.filter(staff_id="EMP-1").count(), 1)
        self.assertEqual(len(self._staff_users()), 1)
        # The existing account was reused (email B never provisioned a user).
        self.assertFalse(User.objects.filter(email__iexact="jane.doe@newmail.com").exists())
        self.assertEqual(TeacherProfile.objects.get(staff_id="EMP-1").user_id, first_user.pk)

    def test_reimport_no_email_links_by_staff_id_not_duplicate(self):
        # First import with an email, then the SAME staffer with NO email at all
        # (the phone-primary / email-rare reality) — the pre-fix lander would
        # provision a fresh "first.last" account; staff_id must link instead.
        self._land(self._row(email="jane@ex.com"))
        first_user = TeacherProfile.objects.get(staff_id="EMP-1").user
        b = self._land(self._row())  # no email
        self.assertEqual(b.quarantined, 0, b.errors)
        self.assertEqual(TeacherProfile.objects.filter(staff_id="EMP-1").count(), 1)
        self.assertEqual(len(self._staff_users()), 1)
        self.assertEqual(TeacherProfile.objects.get(staff_id="EMP-1").user_id, first_user.pk)

    def test_staff_id_dedup_is_school_scoped(self):
        # EMP-1 in this school must never be reused for EMP-1 in ANOTHER school.
        self._land(self._row(email="jane@ex.com"))
        other = School.objects.create(name="Other", slug="other-sd", subdomain="other-sd")
        r = self._land(self._row(email="someoneelse@ex.com"), school=other)
        self.assertEqual(r.quarantined, 0, r.errors)
        # A distinct profile + distinct user landed in the other school.
        self.assertEqual(TeacherProfile.objects.filter(staff_id="EMP-1", school=other).count(), 1)
        here = self._staff_users(school=self.school)
        there = self._staff_users(school=other)
        self.assertEqual(len(here), 1)
        self.assertEqual(len(there), 1)
        self.assertTrue(here.isdisjoint(there))

    def test_ambiguous_duplicate_staff_id_does_not_guess_merge(self):
        # Legacy dirty data: two DISTINCT users already share staff_id EMP-1. An
        # incoming EMP-1 under a new identity is ambiguous → provision a fresh
        # account, never guess which of the two it belongs to.
        u1 = User.objects.create_user(username="emp1a", first_name="Jane", last_name="Doe")
        u2 = User.objects.create_user(username="emp1b", first_name="Jane", last_name="Doe")
        TeacherProfile.objects.create(user=u1, school=self.school, staff_id="EMP-1")
        TeacherProfile.objects.create(user=u2, school=self.school, staff_id="EMP-1")
        r = self._land(self._row(email="brandnew@ex.com"))
        self.assertEqual(r.quarantined, 0, r.errors)
        # A third profile was provisioned; neither existing user was mutated.
        self.assertEqual(TeacherProfile.objects.filter(staff_id="EMP-1").count(), 3)
        users = self._staff_users()
        self.assertEqual(len(users), 3)
        self.assertIn(u1.pk, users)
        self.assertIn(u2.pk, users)
        new_user = User.objects.get(email__iexact="brandnew@ex.com")
        self.assertNotIn(new_user.pk, (u1.pk, u2.pk))

    def test_username_ref_resolution_preserved_when_no_staff_id_match(self):
        # No existing profile for this staff_id → the staff_id rung is a no-op
        # and the internal-transfer username path still resolves (no duplicate).
        transfer = User.objects.create_user(username="transferguy", first_name="Kofi", last_name="Ba")
        before = User.objects.count()
        r = self._land(self._row(first="Kofi", last="Ba", staff_ext="EMP-NEW",
                                 staff_user_ref="transferguy"))
        self.assertEqual(r.quarantined, 0, r.errors)
        self.assertEqual(User.objects.count(), before)  # reused, not provisioned
        self.assertEqual(TeacherProfile.objects.get(staff_id="EMP-NEW").user_id, transfer.pk)

    def test_dedup_link_recorded_when_staff_id_saves_a_reimport(self):
        # When the strong-key match links a user email/username would NOT have
        # reached, the auto-link is surfaced on the bundle for operator review.
        bundle = MigrationBundle.objects.create(
            school=self.school, idempotency_key="tier1d-staff-dedup"
        )
        self._land(self._row(email="jane@ex.com"), bundle_id=bundle.pk)
        self._land(self._row(), bundle_id=bundle.pk)  # no email → linked by staff_id
        bundle.refresh_from_db()
        links = (bundle.mapping_summary or {}).get("dedup_links", [])
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["matched_on"], "staff_id")
        self.assertEqual(links[0]["linked_staff_id"], "EMP-1")

    def test_normal_rerun_same_email_stays_quiet(self):
        # A plain idempotent rerun (same email) is not a "dedup save" — no link
        # is recorded, and it still lands exactly one profile.
        bundle = MigrationBundle.objects.create(
            school=self.school, idempotency_key="tier1d-staff-rerun"
        )
        self._land(self._row(email="jane@ex.com"), bundle_id=bundle.pk)
        self._land(self._row(email="jane@ex.com", role="Head"), bundle_id=bundle.pk)
        bundle.refresh_from_db()
        self.assertEqual(TeacherProfile.objects.filter(staff_id="EMP-1").count(), 1)
        self.assertEqual((bundle.mapping_summary or {}).get("dedup_links", []), [])
