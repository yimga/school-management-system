"""M13 -- health clearance: the validity window, and where the block ISN'T.

The audit row reads "health-clearance signoff actually blocks participation".
Tracing every caller of the clearance predicate shows the first half is real and
the second half is not, so this module is deliberately in two parts.

**Part 1 -- the window, which is real and was half-tested.**
``_medical_ok`` (``apps/athletics/services/eligibility.py``) requires a CLEARED
row whose window is open at both ends::

    Q(valid_until__isnull=True) | Q(valid_until__gte=today),
    Q(valid_from__isnull=True)  | Q(valid_from__lte=today),
    status=MedicalClearance.Status.CLEARED,

``MedicalValidFromTests`` in ``test_eligibility.py`` covers the ``valid_from``
arm in three cases. Nothing anywhere covers the ``valid_until`` arm, and nothing
covers the ``status`` arm -- so a regression that dropped either would keep LAST
SEASON's expired clearance, or a PENDING one a doctor never signed, satisfying
medical for the whole year, with the entire existing suite green. Those are the
cases most likely to matter: a clearance lapses on a schedule, and a pending one
is the normal state of a form that was started and not finished.

**Part 2 -- the enforcement point, which does not exist.**
``_medical_ok`` has exactly one consumer, ``resolve_eligibility``, which returns
an ``EligibilityOutcome`` and writes an ``EligibilityRecord``. It raises nothing,
and no caller branches on its result. ``resolve_eligibility`` itself has ONE
production caller: the POST branch of ``coach_eligibility``, a manual recompute
sweep whose result is discarded except for a success-message count, inside
``except Exception: continue``.

Meanwhile the only writer of ``TeamMembership.Status.ACTIVE`` is
``ParticipationConsent.consent()``, which checks the consent token and nothing
else. So an athlete with no clearance at all goes PENDING -> ACTIVE on guardian
consent, and no code path anywhere consults the clearance before that happens.
There is no squad-selection or team-sheet model for a guard to sit on either --
``models/fixtures.py`` defines only ``Fixture``, ``FixtureResult`` and
``FixtureTravel``.

``test_gap_*`` below RECORDS THAT ABSENCE. It is a characterization test, not an
endorsement: it asserts what the system does today so the gap is an executable
fact rather than a paragraph in a report. **When enforcement is added, that test
is SUPPOSED to fail** -- delete it and replace it with the refusal assertion.
Nothing else in this module depends on it.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.athletics.models import MedicalClearance, TeamMembership
from apps.athletics.services.eligibility import resolve_eligibility
from apps.athletics.tests.base import BaseAthleticsTestCase


class MedicalClearanceExpiryWindowTests(BaseAthleticsTestCase):
    """The ``valid_until`` arm -- untested until now."""

    def setUp(self):
        super().setUp()
        self.membership = self.add_member(self.fx, status=TeamMembership.Status.ACTIVE)
        self.today = timezone.now().date()

    def _medical_ok(self) -> bool:
        return resolve_eligibility(
            membership=self.membership, persist=True
        ).record.medical_ok

    def test_a_lapsed_clearance_does_not_satisfy_medical(self):
        """Last season's signoff must not clear an athlete this season."""
        self.make_clearance(
            self.fx,
            status=MedicalClearance.Status.CLEARED,
            valid_from=self.today - timedelta(days=400),
            valid_until=self.today - timedelta(days=1),
        )
        self.assertFalse(self._medical_ok())

    def test_a_clearance_expiring_today_still_satisfies_medical(self):
        """The comparison is ``>= today``: the last day is still a valid day."""
        self.make_clearance(
            self.fx,
            status=MedicalClearance.Status.CLEARED,
            valid_from=self.today - timedelta(days=30),
            valid_until=self.today,
        )
        self.assertTrue(self._medical_ok())

    def test_a_clearance_expiring_tomorrow_satisfies_medical(self):
        self.make_clearance(
            self.fx,
            status=MedicalClearance.Status.CLEARED,
            valid_from=self.today - timedelta(days=30),
            valid_until=self.today + timedelta(days=1),
        )
        self.assertTrue(self._medical_ok())

    def test_an_open_ended_clearance_satisfies_medical(self):
        self.make_clearance(
            self.fx,
            status=MedicalClearance.Status.CLEARED,
            valid_from=self.today - timedelta(days=30),
            valid_until=None,
        )
        self.assertTrue(self._medical_ok())

    def test_a_lapsed_clearance_is_not_rescued_by_a_current_one_expiring(self):
        """Two rows, one lapsed and one live -- the live one must win.

        The predicate is an ``.exists()`` over the filtered set, so this pins
        that a stale row alongside a good one does not poison the result.
        """
        self.make_clearance(
            self.fx,
            status=MedicalClearance.Status.CLEARED,
            valid_from=self.today - timedelta(days=400),
            valid_until=self.today - timedelta(days=200),
        )
        self.assertFalse(self._medical_ok())
        self.make_clearance(
            self.fx,
            status=MedicalClearance.Status.CLEARED,
            valid_from=self.today - timedelta(days=10),
            valid_until=self.today + timedelta(days=100),
        )
        self.assertTrue(self._medical_ok())


class MedicalClearanceStatusArmTests(BaseAthleticsTestCase):
    """Only CLEARED clears. The other three statuses were never asserted."""

    def setUp(self):
        super().setUp()
        self.membership = self.add_member(self.fx, status=TeamMembership.Status.ACTIVE)
        self.today = timezone.now().date()

    def _medical_ok(self) -> bool:
        return resolve_eligibility(
            membership=self.membership, persist=True
        ).record.medical_ok

    def test_a_pending_clearance_does_not_clear_the_athlete(self):
        """A form somebody started is not a doctor's signature."""
        self.make_clearance(
            self.fx,
            status=MedicalClearance.Status.PENDING,
            valid_from=self.today - timedelta(days=1),
            valid_until=self.today + timedelta(days=300),
        )
        self.assertFalse(self._medical_ok())

    def test_a_revoked_clearance_does_not_clear_the_athlete(self):
        self.make_clearance(
            self.fx,
            status=MedicalClearance.Status.REVOKED,
            valid_from=self.today - timedelta(days=1),
            valid_until=self.today + timedelta(days=300),
        )
        self.assertFalse(self._medical_ok())

    def test_an_expired_status_does_not_clear_the_athlete(self):
        self.make_clearance(
            self.fx,
            status=MedicalClearance.Status.EXPIRED,
            valid_from=self.today - timedelta(days=1),
            valid_until=self.today + timedelta(days=300),
        )
        self.assertFalse(self._medical_ok())

    def test_the_same_window_with_CLEARED_does_clear(self):
        """Control. Without this the four negatives above could all be passing
        because the window is wrong, not because the status arm works."""
        self.make_clearance(
            self.fx,
            status=MedicalClearance.Status.CLEARED,
            valid_from=self.today - timedelta(days=1),
            valid_until=self.today + timedelta(days=300),
        )
        self.assertTrue(self._medical_ok())

    def test_a_clearance_belonging_to_another_student_does_not_clear_this_one(self):
        from apps.people.models import StudentProfile

        other = StudentProfile.objects.create(
            school=self.fx.school,
            first_name="Other",
            last_name="Athlete",
            student_code="M13-OTHER-1",
            admission_number="M13-ADM-OTHER-1",
            academic_year=self.fx.year,
            classroom=self.fx.classroom,
            specialty=self.fx.specialty,
        )
        self.make_clearance(
            self.fx,
            student=other,
            status=MedicalClearance.Status.CLEARED,
            valid_from=self.today - timedelta(days=1),
        )
        self.assertFalse(self._medical_ok())
        # ...and the row really is a valid clearance, just for someone else.
        self.assertTrue(
            MedicalClearance.objects.filter(
                student=other, status=MedicalClearance.Status.CLEARED
            ).exists()
        )


class MedicalClearanceEnforcementGapTests(BaseAthleticsTestCase):
    """CHARACTERIZATION -- records an ABSENCE, not a guarantee.

    Read the module docstring before changing anything here. These tests assert
    that the platform does NOT block participation on medical clearance today.
    They exist so the gap is executable and dated rather than filed in a report.
    When an enforcement point is added, these tests must FAIL and be replaced by
    the refusal assertions.
    """

    def setUp(self):
        super().setUp()
        self.today = timezone.now().date()

    def test_gap_an_uncleared_athlete_is_still_resolvable_not_refused(self):
        """``resolve_eligibility`` returns an opinion. It refuses nothing."""
        membership = self.add_member(self.fx, status=TeamMembership.Status.ACTIVE)
        self.assertFalse(
            MedicalClearance.objects.filter(student=self.fx.student).exists()
        )
        outcome = resolve_eligibility(membership=membership, persist=True)

        # It correctly NOTICES the missing clearance...
        self.assertFalse(outcome.record.medical_ok)
        self.assertFalse(outcome.eligible)
        # ...and the membership is untouched by that finding.
        membership.refresh_from_db()
        self.assertEqual(
            membership.status,
            TeamMembership.Status.ACTIVE,
            msg=(
                "membership status changed -- if an enforcement point was added, "
                "delete this characterization test and assert the refusal"
            ),
        )

    def test_gap_the_reason_is_recorded_even_though_nothing_acts_on_it(self):
        """The diagnosis exists; only the treatment is missing.

        This is what makes the gap cheap to close: the predicate, the reason
        string and the persisted record are all already correct.
        """
        membership = self.add_member(self.fx, status=TeamMembership.Status.ACTIVE)
        outcome = resolve_eligibility(membership=membership, persist=True)
        self.assertTrue(
            any("medical" in reason for reason in outcome.reasons),
            msg=f"no medical reason recorded: {outcome.reasons}",
        )
        self.assertIsNotNone(outcome.record)
        self.assertFalse(outcome.record.medical_ok)
