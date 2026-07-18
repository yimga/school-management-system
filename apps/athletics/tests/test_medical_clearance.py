"""M13 seal — the medical-clearance PRODUCER, eligibility flip, and RBAC.

HEAD shipped ``MedicalClearance.Status.CLEARED`` with a CONSUMER
(``services.eligibility._medical_ok``) but NO product path that ever set a
clearance to CLEARED, so ``_medical_ok`` failed closed and no athlete could ever
be ELIGIBLE (best case PROVISIONAL). These tests drive the REAL clearance path —
the ``coach_record_clearance`` view calling the ``record_medical_clearance``
service, NOT a direct ORM fixture — and assert the athlete flips to ELIGIBLE,
plus that an unauthorized user cannot clear.

Fails-first: on HEAD ``coach_record_clearance`` / ``record_medical_clearance``
do not exist (ImportError at collection), and even reproduced by hand the athlete
would remain PROVISIONAL forever.
"""

from __future__ import annotations

from importlib import import_module

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, override_settings

from apps.accounts.models import AccessRole, Permission
from apps.athletics.models import (
    CoachAssignment,
    EligibilityRecord,
    MedicalClearance,
    ParticipationConsent,
    TeamMembership,
)
from apps.athletics.services.eligibility import resolve_eligibility
from apps.athletics.tests.base import BaseAthleticsTestCase
from apps.athletics.views.coach import coach_record_clearance

User = get_user_model()


def _grant(user, *codes):
    role, _ = AccessRole.objects.get_or_create(
        code="ATHLETICS_COACH_MED", defaults={"name": "Coach", "description": "x"}
    )
    for code in codes:
        perm, _ = Permission.objects.get_or_create(
            code=code, defaults={"name": code, "description": code}
        )
        role.permissions.add(perm)
    user.roles.add(role)


@override_settings(ROOT_URLCONF="config.tenant_urls")
class MedicalClearanceProducerTests(BaseAthleticsTestCase):
    """Drive the real clearance path and assert eligibility flips + RBAC holds."""

    def setUp(self):
        super().setUp()
        self.rf = RequestFactory()
        self.membership = self.add_member(
            self.fx, status=TeamMembership.Status.ACTIVE
        )
        # Satisfy the OTHER three predicates so that ONLY the medical predicate
        # stands between the athlete and ELIGIBLE.
        self.make_evaluation(self.fx, exam_score=80)        # academic ok (80% >= 50)
        self.make_attendance(self.fx, present=4, absent=0)  # attendance ok (100% >= 75)
        _raw, consent = ParticipationConsent.mint(
            membership=self.membership,
            guardian_name="Parent",
            guardian_email="parent@example.com",
            consent_text="I consent.",
        )
        consent.consent()  # consent ok

    def _user(self, username, *codes, assign_team=None):
        user = User.objects.create_user(username=username, password="pass123")
        if hasattr(user, "role"):
            user.role = User.Role.TEACHER
            user.save(update_fields=["role"])
        if codes:
            _grant(user, *codes)
        if assign_team is not None:
            CoachAssignment.objects.create(
                school=self.fx.school, team=assign_team, coach=user, is_active=True
            )
        return user

    def _post(self, user):
        request = self.rf.post(
            f"/athletics/memberships/{self.membership.id}/record-clearance/"
        )
        request.user = user
        request.school = self.fx.school
        engine = import_module(settings.SESSION_ENGINE)
        request.session = engine.SessionStore()
        request._messages = FallbackStorage(request)
        request.urlconf = "config.tenant_urls"
        return request

    def test_head_state_athlete_cannot_be_eligible_without_producer(self):
        # Guard/invariant: with the other three predicates satisfied but NO
        # clearance on record, the resolver can only reach PROVISIONAL — the
        # exact ceiling every athlete was stuck under on HEAD.
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertFalse(outcome.record.medical_ok)
        self.assertEqual(outcome.status, EligibilityRecord.Status.PROVISIONAL)
        self.assertFalse(outcome.eligible)

    def test_clearance_view_flips_athlete_to_eligible(self):
        coach = self._user(
            "assigned_med_coach", "athletics.manage", assign_team=self.fx.team
        )
        resp = coach_record_clearance(
            self._post(coach), membership_id=self.membership.id
        )
        self.assertEqual(resp.status_code, 302)  # redirect back to the roster

        # A real CLEARED clearance was produced, signed by the acting coach.
        clearance = MedicalClearance.objects.get(
            school=self.fx.school,
            student=self.membership.student,
            status=MedicalClearance.Status.CLEARED,
        )
        self.assertEqual(clearance.cleared_by_id, coach.id)
        self.assertIsNotNone(clearance.valid_from)
        self.assertIsNotNone(clearance.valid_until)
        self.assertEqual(clearance.sport_id, self.fx.sport.id)

        # The athlete can NOW be ELIGIBLE via the real path.
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertTrue(outcome.record.medical_ok)
        self.assertTrue(outcome.eligible)
        self.assertEqual(outcome.status, EligibilityRecord.Status.ELIGIBLE)

    def test_unauthorized_user_without_grant_cannot_record_clearance(self):
        # Holds no athletics grant -> require_permission denies (PermissionDenied),
        # so no clearance is produced and the athlete stays non-eligible.
        nobody = self._user("nobody_med")
        with self.assertRaises(PermissionDenied):
            coach_record_clearance(
                self._post(nobody), membership_id=self.membership.id
            )
        self.assertFalse(
            MedicalClearance.objects.filter(
                school=self.fx.school,
                student=self.membership.student,
                status=MedicalClearance.Status.CLEARED,
            ).exists()
        )
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertFalse(outcome.eligible)

    def test_manage_grant_but_unassigned_coach_is_object_denied(self):
        # Has athletics.manage but is NOT the admin tier and has NO CoachAssignment
        # for this team -> object-level assert_team_manage denies. Same gate as the
        # other roster write surfaces (add-member / request-consent).
        coach = self._user("unassigned_med_coach", "athletics.manage")
        with self.assertRaises(PermissionDenied):
            coach_record_clearance(
                self._post(coach), membership_id=self.membership.id
            )
        self.assertFalse(
            MedicalClearance.objects.filter(
                school=self.fx.school, status=MedicalClearance.Status.CLEARED
            ).exists()
        )

    def test_service_defaults_window_and_stamps_cleared_by(self):
        # Drive the service directly (the other real entry point): defaults the
        # validity window (today .. today+validity) and captures cleared_by.
        from datetime import timedelta

        from django.utils import timezone

        from apps.athletics.constants import MEDICAL_CLEARANCE_VALIDITY_DAYS
        from apps.athletics.services.medical import record_medical_clearance

        actor = self._user("med_staff", "athletics.manage")
        today = timezone.now().date()
        clearance = record_medical_clearance(
            membership=self.membership, actor=actor
        )
        self.assertEqual(clearance.status, MedicalClearance.Status.CLEARED)
        self.assertEqual(clearance.cleared_by_id, actor.id)
        self.assertEqual(clearance.valid_from, today)
        self.assertEqual(
            clearance.valid_until,
            today + timedelta(days=MEDICAL_CLEARANCE_VALIDITY_DAYS),
        )
        outcome = resolve_eligibility(membership=self.membership, persist=True)
        self.assertTrue(outcome.record.medical_ok)
        self.assertTrue(outcome.eligible)
