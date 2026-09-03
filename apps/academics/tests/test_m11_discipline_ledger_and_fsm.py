"""M11 -- discipline points arithmetic and the routing FSM.

Two claims sat unproven, and auditing them found the code did not hold either.

**The FSM.** ``discipline_services`` called itself "Incident routing FSM" but had
no transition map and no refusal. Escalation was guarded by
``incident.status != Incident.Status.REFERRED`` -- which is TRUE for a RESOLVED
incident. So a closed case could be pushed back to REFERRED by any later routing
call: the student silently reappears on the counselor caseload, ``resolved_at``
and ``resolved_by`` still stamped, no error, no log. That is not "the FSM refuses
illegal transitions"; that is the absence of an FSM. Fixed by an explicit
transition map plus ``assert_incident_transition``, mirroring the shape
``lesson_homework_kernel`` already uses for lesson lifecycle.

**The arithmetic.** The point total is an aggregate over ``BehaviorPointLedger``,
which carries no unique constraint, and accrual was an unconditional ``create``.
Any second reach of the producer for the same incident -- a direct service call,
an offline replay, a re-save that re-fires routing -- double-counted the student
toward the escalation threshold. Fixed with ``get_or_create`` keyed on the
incident, the same shape the ``RestorativeAction`` line below it already used.

Existing coverage (``test_discipline_routing.py``, ``portal/test_discipline_resolve.py``)
asserts the happy path and resolve idempotence. Neither had an illegal-transition
case, a double-accrual case, a merit (negative points) case, or a per-severity
arithmetic case -- the four things this module adds.
"""

from __future__ import annotations

import uuid
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.academics.discipline_services import (
    InvalidIncidentTransition,
    assert_incident_transition,
    can_transition_incident,
    process_incident_routing,
    resolve_incident,
    student_behavior_point_total,
)
from apps.academics.models import Incident
from apps.academics.models_discipline import BehaviorPointLedger, RestorativeAction
from apps.people.models import StudentProfile
from apps.schools.models import School

User = get_user_model()


class _DisciplineFixtureMixin:
    def _build(self):
        self.school = School.objects.create(
            name="M11 School",
            slug=f"m11-{uuid.uuid4().hex[:10]}",
            subdomain=f"m11-{uuid.uuid4().hex[:10]}",
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Ama",
            last_name="Ledger",
            student_code=f"M11-{uuid.uuid4().hex[:6]}",
        )
        self.staff = User.objects.create_user(
            username=f"m11-{uuid.uuid4().hex[:8]}",
            email="m11@disc.test",
            password="x",
            role=User.Role.TEACHER,
        )

    def _incident(self, severity, *, status=None):
        incident = Incident.objects.create(
            school=self.school,
            student=self.student,
            incident_type=Incident.Type.BEHAVIOR,
            severity=severity,
            date=date.today(),
            description="fixture",
            notify_parent=False,
        )
        if status is not None:
            Incident.objects.filter(pk=incident.pk).update(status=status)
            incident.refresh_from_db()
        return incident


class IncidentTransitionMapTests(TestCase):
    """The FSM as a decision, not as prose."""

    def test_legal_edges_are_allowed(self):
        self.assertTrue(
            can_transition_incident(Incident.Status.OPEN, Incident.Status.REFERRED)
        )
        self.assertTrue(
            can_transition_incident(Incident.Status.OPEN, Incident.Status.RESOLVED)
        )
        self.assertTrue(
            can_transition_incident(Incident.Status.REFERRED, Incident.Status.RESOLVED)
        )
        # ...and they do not raise.
        assert_incident_transition(Incident.Status.OPEN, Incident.Status.REFERRED)
        assert_incident_transition(Incident.Status.REFERRED, Incident.Status.RESOLVED)

    def test_resolved_is_terminal(self):
        for target in (
            Incident.Status.OPEN,
            Incident.Status.REFERRED,
            Incident.Status.RESOLVED,
        ):
            with self.subTest(target=target):
                self.assertFalse(
                    can_transition_incident(Incident.Status.RESOLVED, target)
                )
                with self.assertRaises(InvalidIncidentTransition):
                    assert_incident_transition(Incident.Status.RESOLVED, target)

    def test_referral_cannot_be_walked_back_to_open(self):
        self.assertFalse(
            can_transition_incident(Incident.Status.REFERRED, Incident.Status.OPEN)
        )
        with self.assertRaises(InvalidIncidentTransition):
            assert_incident_transition(
                Incident.Status.REFERRED, Incident.Status.OPEN
            )

    def test_an_unknown_status_transitions_nowhere(self):
        self.assertFalse(can_transition_incident("bogus", Incident.Status.RESOLVED))
        with self.assertRaises(InvalidIncidentTransition):
            assert_incident_transition("bogus", Incident.Status.RESOLVED)

    def test_the_refusal_names_the_edge(self):
        with self.assertRaises(InvalidIncidentTransition) as ctx:
            assert_incident_transition(
                Incident.Status.RESOLVED, Incident.Status.REFERRED
            )
        # Django's Choices __repr__ renders the MEMBER NAME
        # ("Incident.Status.RESOLVED"), not the stored value, so match
        # case-insensitively: what matters is that both ends of the rejected
        # edge are named, not which spelling the enum happens to use.
        message = str(ctx.exception).lower()
        self.assertIn("resolved", message)
        self.assertIn("referred", message)
        self.assertIn("illegal", message)


class ResolvedIncidentIsNotReopenedTests(_DisciplineFixtureMixin, TestCase):
    """The edge that actually bit: RESOLVED -> REFERRED via routing."""

    def setUp(self):
        self._build()

    def test_routing_a_resolved_incident_does_not_reopen_it(self):
        # Build a student already past the escalation threshold (2 x HIGH = 10).
        first = self._incident(Incident.Severity.HIGH)
        second = self._incident(Incident.Severity.HIGH)
        self.assertGreaterEqual(
            student_behavior_point_total(school=self.school, student=self.student),
            10,
            msg="fixture never reached the escalation threshold -- branch unreachable",
        )

        resolve_incident(incident=second, resolved_by=self.staff)
        second.refresh_from_db()
        self.assertEqual(second.status, Incident.Status.RESOLVED)
        resolved_at = second.resolved_at
        self.assertIsNotNone(resolved_at)

        # Routing runs again over the closed case (offline replay / direct call).
        outcome = process_incident_routing(incident=second, recorded_by=self.staff)

        second.refresh_from_db()
        self.assertEqual(
            second.status,
            Incident.Status.RESOLVED,
            msg="a resolved incident was silently reopened to REFERRED",
        )
        self.assertEqual(second.resolved_at, resolved_at)
        self.assertFalse(outcome["escalated"])
        self.assertTrue(outcome["escalation_refused"])

        # The first incident is untouched collateral proof the fixture was live.
        first.refresh_from_db()
        self.assertIn(
            first.status, {Incident.Status.OPEN, Incident.Status.REFERRED}
        )

    def test_an_open_incident_over_threshold_still_escalates(self):
        """The refusal must not have broken the legal edge it guards."""
        self._incident(Incident.Severity.HIGH)
        last = self._incident(Incident.Severity.HIGH)
        last.refresh_from_db()
        self.assertEqual(last.status, Incident.Status.REFERRED)

    def test_resolve_is_idempotent_and_reports_it(self):
        incident = self._incident(Incident.Severity.LOW)
        first = resolve_incident(incident=incident, resolved_by=self.staff)
        self.assertTrue(first["resolved"])
        second = resolve_incident(incident=incident, resolved_by=self.staff)
        self.assertFalse(second["resolved"])
        self.assertTrue(second["already_resolved"])
        incident.refresh_from_db()
        self.assertEqual(incident.status, Incident.Status.RESOLVED)


class PointsLedgerArithmeticTests(_DisciplineFixtureMixin, TestCase):
    """The number on the counselor's screen, computed the hard way."""

    def setUp(self):
        self._build()

    def test_severity_maps_to_exact_points(self):
        cases = (
            (Incident.Severity.LOW, 1),
            (Incident.Severity.MEDIUM, 3),
            (Incident.Severity.HIGH, 5),
        )
        running = 0
        for severity, expected in cases:
            with self.subTest(severity=severity):
                self._incident(severity)
                running += expected
                self.assertEqual(
                    student_behavior_point_total(
                        school=self.school, student=self.student
                    ),
                    running,
                )

    def test_total_is_the_sum_of_every_ledger_row(self):
        self._incident(Incident.Severity.HIGH)
        self._incident(Incident.Severity.MEDIUM)
        self._incident(Incident.Severity.LOW)
        rows = BehaviorPointLedger.objects.filter(
            school=self.school, student=self.student
        )
        self.assertEqual(rows.count(), 3)
        self.assertEqual(
            student_behavior_point_total(school=self.school, student=self.student),
            sum(row.points for row in rows),
        )
        self.assertEqual(
            student_behavior_point_total(school=self.school, student=self.student), 9
        )

    def test_merit_rows_subtract(self):
        """``points`` is documented as a SIGNED delta -- negative is a merit.

        Nothing asserted that the aggregate honours the sign, so a total that
        silently used ``abs()`` or filtered ``points__gt=0`` would have passed.
        """
        self._incident(Incident.Severity.HIGH)  # +5
        BehaviorPointLedger.objects.create(
            school=self.school,
            student=self.student,
            points=-4,
            reason="Merit: helped a peer",
            recorded_by=self.staff,
        )
        self.assertEqual(
            student_behavior_point_total(school=self.school, student=self.student), 1
        )

    def test_a_student_with_no_ledger_rows_totals_zero(self):
        clean = StudentProfile.objects.create(
            school=self.school,
            first_name="Zero",
            last_name="Rows",
            student_code=f"M11Z-{uuid.uuid4().hex[:6]}",
        )
        self.assertEqual(
            student_behavior_point_total(school=self.school, student=clean), 0
        )

    def test_totals_do_not_bleed_between_students(self):
        other = StudentProfile.objects.create(
            school=self.school,
            first_name="Other",
            last_name="Student",
            student_code=f"M11O-{uuid.uuid4().hex[:6]}",
        )
        self._incident(Incident.Severity.HIGH)
        self.assertEqual(
            student_behavior_point_total(school=self.school, student=self.student), 5
        )
        self.assertEqual(
            student_behavior_point_total(school=self.school, student=other), 0
        )

    def test_totals_do_not_bleed_between_schools(self):
        self._incident(Incident.Severity.HIGH)
        other_school = School.objects.create(
            name="M11 Other School",
            slug=f"m11x-{uuid.uuid4().hex[:10]}",
            subdomain=f"m11x-{uuid.uuid4().hex[:10]}",
        )
        self.assertEqual(
            student_behavior_point_total(
                school=other_school, student=self.student
            ),
            0,
        )


class LedgerAccrualIsIdempotentTests(_DisciplineFixtureMixin, TestCase):
    """One incident, one accrual -- no matter how often routing is reached."""

    def setUp(self):
        self._build()

    def test_rerunning_routing_does_not_double_count(self):
        incident = self._incident(Incident.Severity.HIGH)
        self.assertEqual(
            student_behavior_point_total(school=self.school, student=self.student), 5
        )
        self.assertEqual(
            BehaviorPointLedger.objects.filter(incident=incident).count(), 1
        )

        for _ in range(3):
            outcome = process_incident_routing(
                incident=incident, recorded_by=self.staff
            )
            self.assertFalse(outcome["points_accrued"])
            self.assertEqual(outcome["points_added"], 0)

        self.assertEqual(
            BehaviorPointLedger.objects.filter(incident=incident).count(),
            1,
            msg="routing double-accrued the same incident",
        )
        self.assertEqual(
            student_behavior_point_total(school=self.school, student=self.student),
            5,
            msg="replayed routing inflated the point total",
        )

    def test_replay_does_not_manufacture_an_escalation(self):
        """A single MEDIUM incident replayed four times used to reach 12 points
        and escalate a student who had done one thing wrong."""
        incident = self._incident(Incident.Severity.MEDIUM)
        for _ in range(4):
            process_incident_routing(incident=incident, recorded_by=self.staff)
        incident.refresh_from_db()
        self.assertEqual(
            student_behavior_point_total(school=self.school, student=self.student), 3
        )
        self.assertEqual(
            incident.status,
            Incident.Status.OPEN,
            msg="a replayed single incident escalated the student",
        )

    def test_distinct_incidents_still_accrue_separately(self):
        """The guard is per-incident, not a blanket 'only ever accrue once'."""
        self._incident(Incident.Severity.MEDIUM)
        self._incident(Incident.Severity.MEDIUM)
        self.assertEqual(
            BehaviorPointLedger.objects.filter(
                school=self.school, student=self.student
            ).count(),
            2,
        )
        self.assertEqual(
            student_behavior_point_total(school=self.school, student=self.student), 6
        )

    def test_restorative_action_is_not_duplicated_on_replay(self):
        incident = self._incident(Incident.Severity.HIGH)
        for _ in range(3):
            process_incident_routing(incident=incident, recorded_by=self.staff)
        self.assertEqual(
            RestorativeAction.objects.filter(
                school=self.school, incident=incident
            ).count(),
            1,
        )
