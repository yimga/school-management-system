"""The two measured-stranded school-data domains, now on the rail -- each by its shape.

Measured 2026-09-02 (docs/audits/…edge-write-reachability.md): the behavior
domain's ``academics.Incident`` and the guardians domain's
``people.StudentGuardian`` reached the cloud NOWHERE from a box import --
silently, with no error, conflict or refusal. Registered 2026-09-03, but not
identically, because their shapes differ where it matters:

*   ``incident`` rides two-way and is INSERTABLE. Offline discipline logging is
    a primary use of the appliance; nothing on the row grants access or moves
    money, and its User FKs (created_by/resolved_by) are nullable and dropped by
    derivation, so who-resolved-it stays a local audit detail while WHAT
    happened converges.
*   ``student_guardian`` rides INSERT-HELD with a down-only authorization core.
    The link names an ``accounts.User`` and grants that person access to a
    child's records: contact edits (phone, relationship, preferences) converge
    two-way, creation stays an identity decision, and
    can_view_finance / can_view_results / is_active / merged_into ride
    down-only -- authorization and merge governance are the cloud's to grant,
    never a stale box's.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.academics.models import Incident
from apps.api.sync_services import (
    _DOWN_ONLY_FIELDS_PER_ENTITY,
    _INSERT_HELD_ENTITIES,
    _get_entity_config,
    _sync_conflict_policy,
    apply_edge_inserts,
)
from apps.people.models import StudentGuardian, StudentProfile
from apps.schools.models import School
from apps.sync_engine.policy_registry import MergeStrategy


def _school():
    return School.objects.first() or School.objects.create(
        name="Stranded High", slug="stranded-high", subdomain="strandedhigh"
    )


class RegistrationTests(TestCase):
    def test_both_entities_ride_the_edge_registry_only(self):
        edge = _get_entity_config(include_derived=True)
        online = _get_entity_config(include_derived=False)
        for entity in ("incident", "student_guardian"):
            self.assertIn(entity, edge)
            self.assertNotIn(entity, online)

    def test_incident_carries_the_record_not_the_audit_identities(self):
        _model, allowed = _get_entity_config(include_derived=True)["incident"]
        for f in ("incident_type", "date", "severity", "status", "student_id", "resolved_at"):
            self.assertIn(f, allowed, f)
        # Nullable User FKs are dropped by derivation: who-created/resolved stays
        # a local audit detail; a login pk must never ride between pk spaces.
        self.assertNotIn("created_by_id", allowed)
        self.assertNotIn("resolved_by_id", allowed)

    def test_guardian_link_carries_contact_never_the_login(self):
        _model, allowed = _get_entity_config(include_derived=True)["student_guardian"]
        for f in ("relationship", "phone", "email", "student_id", "preferred_contact"):
            self.assertIn(f, allowed, f)
        # THE load-bearing drop: the accounts.User FK does not ride. The two
        # deployments mint user pks in unrelated spaces, and a link that names
        # the wrong person grants the wrong person access to a child's records.
        self.assertNotIn("guardian_user_id", allowed)

    def test_both_declare_causal_lww_and_stay_unprotected(self):
        # Protected stays exactly marks and money; these two are handled
        # structurally (insert-held + down-only), not by protection.
        for entity in ("incident", "student_guardian"):
            strategy, protected = _sync_conflict_policy(entity)
            self.assertEqual(strategy, MergeStrategy.CAUSAL_LWW, entity)
            self.assertFalse(protected, entity)

    def test_guardian_authorization_core_is_down_only(self):
        down = _DOWN_ONLY_FIELDS_PER_ENTITY["student_guardian"]
        self.assertEqual(
            down, {"can_view_finance", "can_view_results", "is_active", "merged_into_id"}
        )
        self.assertIn("student_guardian", _INSERT_HELD_ENTITIES)
        self.assertNotIn("incident", _INSERT_HELD_ENTITIES)


class ApplyPathTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = _school()
        cls.staff = get_user_model().objects.create_user(
            username="stranded_staff",
            password="Test1234",
            email="stranded_staff@test.com",
            is_staff=True,
        )
        cls.student = StudentProfile.objects.create(
            school=cls.school,
            first_name="Ndip",
            last_name="Arrey",
            student_code="STR-001",
        )

    def test_a_box_created_incident_lands_by_anchor(self):
        out = apply_edge_inserts(
            self.school.pk,
            self.staff,
            [
                {
                    "entity_type": "incident",
                    "id": 4242,  # the box's local pk: recorded for remap, never trusted
                    "client_offline_id": "box-incident-1",
                    "changes": {
                        "incident_type": Incident.Type.TARDINESS,
                        "date": "2026-09-01",
                        "severity": Incident.Severity.LOW,
                        "status": Incident.Status.OPEN,
                        "student_id": self.student.pk,
                        "description": "arrived after first period",
                    },
                    "updated_at": "2026-09-01T09:00:00+00:00",
                }
            ],
            sync_origin="edge-push",
        )
        self.assertEqual(out["created"], 1, out)
        row = Incident.objects.get(school=self.school, client_offline_id="box-incident-1")
        self.assertEqual(row.student_id, self.student.pk)
        self.assertEqual(row.status, Incident.Status.OPEN)
        self.assertIsNotNone(row.updated_at)

    def test_a_box_created_guardian_link_is_refused_with_the_reason(self):
        out = apply_edge_inserts(
            self.school.pk,
            self.staff,
            [
                {
                    "entity_type": "student_guardian",
                    "id": 77,
                    "client_offline_id": "box-guardian-1",
                    "changes": {
                        "relationship": StudentGuardian.Relationship.MOTHER,
                        "phone": "677 00 11 22",
                        "student_id": self.student.pk,
                    },
                    "updated_at": "2026-09-01T09:00:00+00:00",
                }
            ],
            sync_origin="edge-push",
        )
        self.assertEqual(out["created"], 0)
        result = out["results"][0]
        self.assertEqual(result["status"], 409)
        self.assertEqual(result["data"]["error"], "insert_held_for_entity")
        self.assertIn("access", result["data"]["reason"])
        self.assertFalse(
            StudentGuardian.objects.filter(client_offline_id="box-guardian-1").exists()
        )


class GuardianOwnershipTests(TestCase):
    def test_save_aligns_school_with_the_student(self):
        school = _school()
        student = StudentProfile.objects.create(
            school=school,
            first_name="Bih",
            last_name="Fru",
            student_code="STR-002",
        )
        parent = get_user_model().objects.create_user(
            username="stranded_parent",
            password="Test1234",
            email="stranded_parent@test.com",
        )
        parent.role = get_user_model().Role.PARENT
        parent.save(update_fields=["role"])
        link = StudentGuardian.objects.create(guardian_user=parent, student=student)
        self.assertEqual(link.school_id, school.pk)
        self.assertIsNotNone(link.updated_at)
