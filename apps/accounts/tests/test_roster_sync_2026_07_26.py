"""F5c — Clever/ClassLink inbound roster sync (2026-07-26).

Live district pulls are cert-gated (a certified Clever/ClassLink district token),
so the mapping + persistence + orchestrator are exercised against synthetic
Clever / OneRoster-shaped rows via an injected page fetcher, and the management
command is driven with the HTTP client mocked.
"""

from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.accounts.models import User
from apps.interop.roster_sync import (
    RosterSyncError,
    clever_fetch_pages,
    map_clever_user,
    map_oneroster_user,
    record_sync_state,
    resolve_roster_bearer,
    sync_roster_for_school,
    upsert_roster_person,
)
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import ServiceIntegration

CLEVER_USERS = [
    {"data": {"id": "c1", "name": {"first": "Ada", "last": "Lovelace"},
              "email": "ada@school.org", "roles": {"student": {"grade": "10"}}}},
    {"data": {"id": "c2", "name": {"first": "Alan", "last": "Turing"},
              "email": "alan@school.org", "roles": {"teacher": {}}}},
]
ONEROSTER_USERS = [
    {"sourcedId": "o1", "username": "grace", "givenName": "Grace",
     "familyName": "Hopper", "email": "grace@school.org", "role": "student"},
    {"sourcedId": "o2", "username": "linus", "givenName": "Linus",
     "familyName": "Torvalds", "email": "linus@school.org", "role": "administrator"},
]


class RosterMapperTests(TestCase):
    def test_map_clever_student(self):
        person = map_clever_user(CLEVER_USERS[0], User=User)
        self.assertEqual(person["role"], User.Role.STUDENT)
        self.assertTrue(person["is_student"])
        self.assertEqual(person["first_name"], "Ada")
        self.assertEqual(person["last_name"], "Lovelace")
        self.assertEqual(person["email"], "ada@school.org")
        self.assertEqual(person["source_id"], "c1")

    def test_map_clever_teacher(self):
        person = map_clever_user(CLEVER_USERS[1], User=User)
        self.assertEqual(person["role"], User.Role.TEACHER)
        self.assertFalse(person["is_student"])

    def test_map_oneroster_admin(self):
        person = map_oneroster_user(ONEROSTER_USERS[1], User=User)
        self.assertEqual(person["role"], User.Role.ADMIN)
        self.assertEqual(person["username"], "linus")
        self.assertFalse(person["is_student"])

    def test_map_bad_input_returns_none(self):
        self.assertIsNone(map_clever_user("nope", User=User))
        self.assertIsNone(map_oneroster_user(None, User=User))


class RosterUpsertTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Roster School", slug="roster-school", subdomain="roster-school", is_active=True
        )

    def test_upsert_student_creates_user_membership_and_profile(self):
        person = map_clever_user(CLEVER_USERS[0], User=User)
        result = upsert_roster_person(self.school, person, User=User)
        self.assertTrue(result["ok"])
        self.assertTrue(result["created"])
        self.assertTrue(result["is_student"])
        user = User.objects.get(username=person["username"])
        membership = SchoolMembership.objects.get(user=user, school=self.school)
        self.assertEqual(membership.role, User.Role.STUDENT)
        self.assertTrue(StudentProfile.objects.filter(user=user, school=self.school).exists())

    def test_existing_user_global_role_preserved(self):
        # A user who is ADMIN elsewhere must not be demoted globally by a roster.
        existing = User.objects.create_user(
            username="grace", email="grace@school.org", password="x", role=User.Role.ADMIN
        )
        person = map_oneroster_user(ONEROSTER_USERS[0], User=User)  # role student
        upsert_roster_person(self.school, person, User=User)
        existing.refresh_from_db()
        self.assertEqual(existing.role, User.Role.ADMIN)  # global role untouched
        membership = SchoolMembership.objects.get(user=existing, school=self.school)
        self.assertEqual(membership.role, User.Role.STUDENT)  # per-school role applied

    def test_upsert_idempotent(self):
        person = map_clever_user(CLEVER_USERS[0], User=User)
        upsert_roster_person(self.school, person, User=User)
        upsert_roster_person(self.school, person, User=User)
        user = User.objects.get(username=person["username"])
        self.assertEqual(SchoolMembership.objects.filter(user=user, school=self.school).count(), 1)
        self.assertEqual(StudentProfile.objects.filter(user=user).count(), 1)


class RosterOrchestratorTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Orch School", slug="orch-school", subdomain="orch-school", is_active=True
        )

    def test_sync_clever_counts(self):
        stats = sync_roster_for_school(
            self.school, provider="clever", fetch_pages=lambda: iter([list(CLEVER_USERS)]), User=User
        )
        self.assertEqual(stats["seen"], 2)
        self.assertEqual(stats["created"], 2)
        self.assertEqual(stats["students"], 1)
        self.assertEqual(SchoolMembership.objects.filter(school=self.school).count(), 2)

    def test_sync_oneroster_two_pages(self):
        stats = sync_roster_for_school(
            self.school, provider="classlink",
            fetch_pages=lambda: iter([[ONEROSTER_USERS[0]], [ONEROSTER_USERS[1]]]), User=User
        )
        self.assertEqual(stats["seen"], 2)
        self.assertEqual(stats["created"], 2)
        self.assertEqual(stats["students"], 1)

    def test_sync_dry_run_persists_nothing(self):
        stats = sync_roster_for_school(
            self.school, provider="clever", fetch_pages=lambda: iter([list(CLEVER_USERS)]),
            User=User, dry_run=True,
        )
        self.assertEqual(stats["seen"], 2)
        self.assertTrue(stats["dry_run"])
        self.assertEqual(SchoolMembership.objects.filter(school=self.school).count(), 0)

    def test_clever_fetch_pages_error_raises(self):
        with patch(
            "apps.interop.clever_classlink_client.clever_list_users",
            return_value={"error": "http_error", "status": 401},
        ):
            fetch = clever_fetch_pages("token-abcdefgh")
            with self.assertRaises(RosterSyncError):
                sync_roster_for_school(self.school, provider="clever", fetch_pages=fetch, User=User)


class RosterCredsAndCommandTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Cmd School", slug="cmd-school", subdomain="cmd-school", is_active=True
        )
        self.integration = ServiceIntegration.objects.create(
            school=self.school, service_name="OneRoster district API",
            service_type=ServiceIntegration.ServiceType.OAUTH,
            config={"native_clever_bearer": "clever-token-abcdefghij"},
            is_active=True,
        )

    def test_resolve_bearer(self):
        bearer, base, integ = resolve_roster_bearer(self.school, "clever")
        self.assertEqual(bearer, "clever-token-abcdefghij")
        self.assertEqual(integ.pk, self.integration.pk)

    def test_resolve_bearer_absent_returns_empty(self):
        bearer, base, integ = resolve_roster_bearer(self.school, "classlink")
        self.assertEqual(bearer, "")
        self.assertIsNone(integ)

    def test_record_sync_state(self):
        record_sync_state(self.integration, {"provider": "clever", "created": 5})
        self.integration.refresh_from_db()
        self.assertIn("roster_last_sync_at", self.integration.config)
        self.assertEqual(self.integration.config["roster_last_sync_stats"]["created"], 5)
        # The stored bearer survives the state write.
        self.assertEqual(self.integration.config["native_clever_bearer"], "clever-token-abcdefghij")

    def test_command_end_to_end_clever(self):
        with patch(
            "apps.interop.clever_classlink_client.clever_list_users",
            return_value={"data": list(CLEVER_USERS)},
        ):
            call_command("sync_roster", school="cmd-school", provider="clever")
        self.assertEqual(SchoolMembership.objects.filter(school=self.school).count(), 2)
        self.integration.refresh_from_db()
        self.assertEqual(self.integration.config["roster_last_sync_stats"]["created"], 2)

    def test_command_dry_run_writes_nothing(self):
        with patch(
            "apps.interop.clever_classlink_client.clever_list_users",
            return_value={"data": list(CLEVER_USERS)},
        ):
            call_command("sync_roster", school="cmd-school", provider="clever", dry_run=True)
        self.assertEqual(SchoolMembership.objects.filter(school=self.school).count(), 0)

    def test_command_no_bearer_raises(self):
        School.objects.create(name="No Cred", slug="no-cred", subdomain="no-cred", is_active=True)
        with self.assertRaises(CommandError):
            call_command("sync_roster", school="no-cred", provider="clever")
