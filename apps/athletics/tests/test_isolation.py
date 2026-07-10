"""Cross-tenant isolation negatives — school A objects never leak into school B.

Two full tenants are built; every athletics relation created for A must be
invisible to a ``school=B`` query, and the consent/eligibility services must
scope strictly by ``membership.school_id``.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.accounts import effective_access
from apps.accounts.models import AccessRole, Permission
from apps.athletics.models import (
    CoachAssignment,
    EligibilityRecord,
    Fixture,
    MedicalClearance,
    ParticipationConsent,
    ParticipationConsentDecision,
    Team,
    TeamMembership,
)
from apps.athletics.services.eligibility import resolve_eligibility
from apps.athletics.tests.base import AthleticsFixtureMixin

User = get_user_model()


class CrossTenantIsolationTests(AthleticsFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.a = self.build_tenant("a")
        self.b = self.build_tenant("b")

    def test_team_not_visible_to_other_school(self):
        self.assertTrue(Team.objects.filter(school=self.a.school, pk=self.a.team.pk).exists())
        self.assertFalse(Team.objects.filter(school=self.b.school, pk=self.a.team.pk).exists())
        self.assertEqual(Team.objects.filter(school=self.b.school).count(), 1)
        self.assertNotIn(self.a.team, list(Team.objects.filter(school=self.b.school)))

    def test_membership_not_visible_to_other_school(self):
        m = self.add_member(self.a)
        self.assertFalse(
            TeamMembership.objects.filter(school=self.b.school, pk=m.pk).exists()
        )

    def test_fixture_not_visible_to_other_school(self):
        now = timezone.now()
        fixture = Fixture.objects.create(
            school=self.a.school,
            team=self.a.team,
            season=self.a.season,
            opponent_name="Rivals",
            scheduled_start=now,
            scheduled_end=now,
        )
        self.assertFalse(
            Fixture.objects.filter(school=self.b.school, pk=fixture.pk).exists()
        )
        self.assertEqual(Fixture.objects.filter(school=self.b.school).count(), 0)

    def test_eligibility_service_scopes_by_membership_school(self):
        # A membership on A resolves + persists an EligibilityRecord scoped to A.
        m = self.add_member(self.a)
        outcome = resolve_eligibility(membership=m, persist=True)
        self.assertEqual(outcome.record.school_id, self.a.school.pk)
        self.assertTrue(
            EligibilityRecord.objects.filter(school=self.a.school, membership=m).exists()
        )
        self.assertFalse(
            EligibilityRecord.objects.filter(school=self.b.school, membership=m).exists()
        )

    def test_consent_service_scopes_by_membership_school(self):
        m = self.add_member(self.a, status=TeamMembership.Status.PENDING)
        raw, consent = ParticipationConsent.mint(
            membership=m,
            guardian_name="Parent A",
            guardian_email="parent.a@example.com",
            consent_text="I consent.",
        )
        self.assertEqual(consent.school_id, self.a.school.pk)
        self.assertFalse(
            ParticipationConsent.objects.filter(
                school=self.b.school, pk=consent.pk
            ).exists()
        )
        # A consent lookup for the B membership graph does not find A's consent.
        self.assertFalse(
            ParticipationConsent.objects.filter(
                school_id=self.b.school.pk,
                membership__student_id=self.a.student.pk,
                decision=ParticipationConsentDecision.PENDING,
            ).exists()
        )

    def test_medical_clearance_not_visible_to_other_school(self):
        clearance = MedicalClearance.objects.create(
            school=self.a.school,
            student=self.a.student,
            status=MedicalClearance.Status.CLEARED,
            notes="Fit to play.",
        )
        self.assertFalse(
            MedicalClearance.objects.filter(
                school=self.b.school, pk=clearance.pk
            ).exists()
        )

    def test_coach_cannot_manage_other_schools_team(self):
        # A coach holds a (school-agnostic) athletics.manage grant + an active
        # CoachAssignment for school A's team. Object-level authority must stay
        # scoped: querying the SAME team id under school B's context denies.
        coach = User.objects.create_user(username="cross_coach", password="x")
        perm, _ = Permission.objects.get_or_create(
            code="athletics.manage",
            defaults={"name": "athletics.manage", "description": "x"},
        )
        role, _ = AccessRole.objects.get_or_create(
            code="ATHLETICS_COACH", defaults={"name": "Coach", "description": "x"}
        )
        role.permissions.add(perm)
        coach.roles.add(role)
        CoachAssignment.objects.create(
            school=self.a.school, team=self.a.team, coach=coach, is_active=True
        )
        self.assertTrue(
            effective_access.athletics_team_manage_access(
                coach, self.a.school, self.a.team.id
            )
        )
        self.assertFalse(
            effective_access.athletics_team_manage_access(
                coach, self.b.school, self.a.team.id
            )
        )
