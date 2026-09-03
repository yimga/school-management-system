"""Tier 1c A-Z upgrade wave (2026-08-08): phone-first guardian dedup.

The guardian's identity is a platform ``User``; ``_resolve_or_provision_user``
matched only on exact username / email, then PROVISIONED a new account. In the
phone-primary, email-rare regions this platform serves, the SAME guardian
re-appearing for a sibling under an inconsistent / absent email was therefore
re-provisioned as a DUPLICATE account (or, with no email at all, quarantined and
lost). This adds a phone-first second-chance to the resolution ladder
(username → email → EXACT phone + matching name → provision).

A row that reaches the final rung with NO email is no longer lost either: it
provisions an account on a reserved, undeliverable ``@unclaimed.invalid``
address minted from a STABLE school+phone+name seed. That seed is what keeps
the no-email path inside this file’s contract — it is resolved before
provisioning, so a re-apply or a sibling row reuses the one account instead
of minting a duplicate.

Safety is the point — a shared household phone (mum + dad on one number) can
never wrong-merge two guardians: the name score must clear the floor AND exactly
one distinct user may match.

Each test fails against the pre-Tier-1c lander (which provisions/quarantines
instead of linking by phone).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.email_delivery_policy import is_deliverable_email
from apps.migration_cloud.landers.guardian_lander import GuardianLander
from apps.migration_cloud.tests.test_landers_fk_resolution import _GraphFixtureMixin
from apps.people.models import StudentGuardian, StudentProfile
from apps.schools.models import School, SchoolMembership

User = get_user_model()


class _Base(_GraphFixtureMixin, TestCase):
    def setUp(self):
        self.fx = self._build_school("gp")
        self.school = self.fx["school"]
        self.student_a = self.fx["student"]  # admission_number ADM-gp-1
        self.student_b = StudentProfile.objects.create(
            school=self.school, first_name="Sib", last_name="Ling",
            admission_number="ADM-gp-2",
            academic_year=self.fx["year"], classroom=self.fx["classroom"],
            specialty=self.fx["specialty"],
        )

    def _row(self, student_ext, first="Ama", last="Mensah", **over):
        row = {
            "student_external_id": student_ext,
            "first_name": first, "last_name": last,
            "relationship": "MOTHER",
        }
        row.update(over)
        return row

    def _land(self, *rows):
        return GuardianLander().land(
            canonical_rows=iter(rows), ctx=self._ctx(self.school)
        )

    def _distinct_guardian_users(self):
        return set(
            StudentGuardian.objects.values_list("guardian_user_id", flat=True)
        )


class GuardianPhoneDedupTests(_Base):
    def test_sibling_no_email_links_by_phone_not_duplicates(self):
        # Child A: provisions the guardian account + a link carrying the phone.
        a = self._land(self._row("ADM-gp-1", email="ama@ex.com", phone="+237600001"))
        self.assertEqual(a.errors, [])
        # Child B (sibling): SAME phone + name, NO email — must link to the same
        # account, not provision a duplicate, not quarantine.
        b = self._land(self._row("ADM-gp-2", phone="+237600001"))
        self.assertEqual(b.quarantined, 0, b.errors)
        link_a = StudentGuardian.objects.get(student=self.student_a)
        link_b = StudentGuardian.objects.get(student=self.student_b)
        self.assertEqual(link_b.guardian_user_id, link_a.guardian_user_id)
        self.assertEqual(len(self._distinct_guardian_users()), 1)

    def test_no_email_no_phone_provisions_one_unclaimed_account_not_duplicates(self):
        """With nothing to dedup ON, the STABLE synthetic address does the job.

        A guardian carrying only a name matches no rung — not ref, not email,
        not phone — so the ladder provisions. It used to quarantine, which lost
        the parent; it now mints an undeliverable ``@unclaimed.invalid``
        address derived from a school+phone+name seed. Because that seed is
        stable AND resolved before provisioning, this path still honours the
        promise the whole file exists for: the SAME guardian is never
        re-provisioned as a duplicate. A re-applied bundle and a second
        SIBLING row must both land on the ONE account.
        """
        first = self._land(self._row("ADM-gp-1"))
        self.assertEqual(first.quarantined, 0, first.errors)
        self.assertEqual(first.created, 1)
        # Re-apply the SAME row: it must resolve back, not re-provision.
        again = self._land(self._row("ADM-gp-1"))
        self.assertEqual(again.quarantined, 0, again.errors)
        self.assertEqual(again.created, 0)
        self.assertEqual(len(self._distinct_guardian_users()), 1)
        # Now the SIBLING row for that same guardian.
        sibling = self._land(self._row("ADM-gp-2"))
        self.assertEqual(sibling.quarantined, 0, sibling.errors)
        self.assertEqual(sibling.created, 1)  # a new LINK, not a new user
        self.assertEqual(len(self._distinct_guardian_users()), 1)
        self.assertEqual(StudentGuardian.objects.count(), 2)
        user = StudentGuardian.objects.first().guardian_user
        self.assertTrue(user.email.endswith("@unclaimed.invalid"), user.email)
        self.assertFalse(is_deliverable_email(user.email))
        self.assertFalse(user.has_usable_password())
        # No second account hiding behind a suffixed username.
        self.assertEqual(User.objects.filter(email__iexact=user.email).count(), 1)

    def test_shared_phone_different_name_provisions_separately(self):
        # Mum, then dad on the SAME household phone — different names must NOT
        # merge into one account.
        self._land(self._row("ADM-gp-1", first="Ama", email="ama@ex.com", phone="+237600001"))
        self._land(self._row("ADM-gp-2", first="Kofi", email="kofi@ex.com", phone="+237600001"))
        self.assertEqual(len(self._distinct_guardian_users()), 2)
        link_b = StudentGuardian.objects.get(student=self.student_b)
        self.assertEqual((link_b.guardian_user.first_name or "").lower(), "kofi")

    def test_ambiguous_same_name_and_phone_does_not_merge(self):
        # Two DISTINCT existing users share name + phone (e.g. Sr & Jr). An
        # incoming match to BOTH is ambiguous → provision, never guess-merge.
        u1 = User.objects.create_user(username="ama1", first_name="Ama", last_name="Mensah")
        u2 = User.objects.create_user(username="ama2", first_name="Ama", last_name="Mensah")
        StudentGuardian.objects.create(student=self.student_a, guardian_user=u1, phone="+237600001", relationship="MOTHER")
        StudentGuardian.objects.create(student=self.student_b, guardian_user=u2, phone="+237600001", relationship="MOTHER")
        # Land a new guardian for student A carrying that name + phone + a NEW email.
        r = self._land(self._row("ADM-gp-1", email="amanew@ex.com", phone="+237600001"))
        self.assertEqual(r.quarantined, 0, r.errors)
        users = self._distinct_guardian_users()
        self.assertEqual(len(users), 3)  # u1, u2, + the freshly provisioned one
        self.assertNotIn(None, users)

    def test_email_match_still_wins_over_phone(self):
        target = User.objects.create_user(username="target", email="target@ex.com",
                                          first_name="Some", last_name="One")
        phone_user = User.objects.create_user(username="phoneguy", first_name="Ama", last_name="Mensah")
        StudentGuardian.objects.create(student=self.student_a, guardian_user=phone_user,
                                       phone="+237600001", relationship="MOTHER")
        # Incoming has BOTH the matching email and the matching phone — email
        # resolution runs first, so it wins.
        self._land(self._row("ADM-gp-2", email="target@ex.com", phone="+237600001"))
        link_b = StudentGuardian.objects.get(student=self.student_b)
        self.assertEqual(link_b.guardian_user_id, target.pk)

    def test_phone_dedup_is_school_scoped(self):
        """A phone held by ANOTHER school’s guardian must never match.

        ``User`` is a SHARED public-schema table, so an unscoped phone rung
        would bind school B’s guardian account into school A’s directory
        (and, via ``ensure_school_membership``, into A’s parent roster). The
        refusal used to be observable as a quarantine; the ladder now falls
        through to provisioning instead, so the contract is asserted where it
        actually lives: the foreign account is NOT linked here, gains NO
        membership here, and a SEPARATE account is minted for this school.
        """
        other = School.objects.create(name="Other", slug="other-gp", subdomain="other-gp")
        other_student = StudentProfile.objects.create(
            school=other, first_name="X", last_name="Y", admission_number="OTH-1"
        )
        other_user = User.objects.create_user(username="otherguardian", first_name="Ama", last_name="Mensah")
        StudentGuardian.objects.create(student=other_student, guardian_user=other_user,
                                       phone="+237600001", relationship="MOTHER")
        # Land in self.school with that phone + no email: the cross-tenant
        # match is refused, so it falls through to unclaimed provisioning.
        r = self._land(self._row("ADM-gp-2", phone="+237600001"))
        self.assertEqual(r.quarantined, 0, r.errors)
        link = StudentGuardian.objects.get(student=self.student_b)
        self.assertNotEqual(link.guardian_user_id, other_user.pk)
        self.assertTrue(link.guardian_user.email.endswith("@unclaimed.invalid"))
        # The other tenant’s account gained nothing in this school.
        self.assertFalse(
            SchoolMembership.objects.filter(
                user=other_user, school=self.school
            ).exists()
        )
        self.assertFalse(
            StudentGuardian.objects.filter(
                guardian_user=other_user, student__school=self.school
            ).exists()
        )
