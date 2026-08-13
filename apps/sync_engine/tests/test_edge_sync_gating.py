"""Phase 5 (+ review) — isolation of the edge feature, so other tenants are untouched.

Two independent gates:
  * ENTITY SCOPE (tenant isolation, flag-independent): the expanded two-way registry is
    scoped to EDGE SYNC operations (_get_entity_config(include_derived=True) / apply with a
    sync_origin). An ordinary online DeltaSyncAPI call (sync_origin None) always sees only
    the original three entities — on ANY deployment, including a shared cloud that serves
    edge boxes. This does not depend on RMC_EDGE_SYNC_ENABLED.
  * AUTO-RUN (RMC_EDGE_SYNC_ENABLED): only where the flag is set does the scheduled
    edge_sync_cycle actually push/pull; elsewhere it is a hard no-op.
"""
from __future__ import annotations

import uuid

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from unittest.mock import patch

from apps.accounts.models import User
from apps.api.sync_services import _get_entity_config, apply_changes
from apps.people.models import StudentNote
from apps.schools.models import School, SchoolMembership

_ORIGINAL_THREE = {"student", "attendance", "classroom"}
_DERIVED = {"applicant", "student_note", "academic_year", "term", "department"}

_CYCLE = "apps.sync_engine.management.commands.edge_sync_cycle.call_command"


class EntityRegistryScopeTests(SimpleTestCase):
    def test_online_callers_get_only_the_original_three(self):
        # The default (online / non-edge) registry — what every ordinary tenant sees.
        self.assertEqual(set(_get_entity_config()), _ORIGINAL_THREE)
        self.assertEqual(set(_get_entity_config(include_derived=False)), _ORIGINAL_THREE)

    def test_edge_operations_get_the_expanded_registry(self):
        entities = set(_get_entity_config(include_derived=True))
        self.assertTrue(_ORIGINAL_THREE <= entities)
        self.assertTrue(_DERIVED <= entities, entities)


class EdgeOperationGatingIntegrationTests(TestCase):
    """The scope gate end-to-end through apply_changes: an online delta of a derived
    entity is rejected; the same row via an edge sync operation applies."""

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Sc {uid}", slug=f"sc-{uid}", subdomain=f"sc{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"sc_admin_{uid}", password="Test1234", email=f"s{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.note = StudentNote.objects.create(school=self.school, body="Base", kind="note")

    def _apply(self, sync_origin):
        return apply_changes(
            str(self.school.id), self.user,
            [{"entity_type": "student_note", "id": self.note.pk,
              "changes": {"body": "Edited"}, "updated_at": "2099-01-01T00:00:00Z"}],
            persist_conflicts=True, sync_origin=sync_origin,
        )

    def test_online_delta_cannot_touch_a_derived_entity(self):
        out = self._apply(sync_origin=None)  # ordinary DeltaSyncAPI path
        self.assertEqual(out["success_count"], 0, out)
        self.assertEqual(out["results"][0]["status"], 400)  # entity_type not in the online config
        self.note.refresh_from_db()
        self.assertEqual(self.note.body, "Base")  # untouched

    def test_edge_sync_can_apply_a_derived_entity(self):
        out = self._apply(sync_origin="cloud-pull")
        self.assertEqual(out["success_count"], 1, out)
        self.note.refresh_from_db()
        self.assertEqual(self.note.body, "Edited")


class EdgeSyncCycleGateTests(SimpleTestCase):
    @override_settings(RMC_EDGE_SYNC_ENABLED=False)
    def test_cycle_is_noop_when_flag_off(self):
        with patch(_CYCLE) as sub:
            call_command("edge_sync_cycle")
        sub.assert_not_called()

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_cycle_runs_push_then_pull_when_flag_on(self):
        with patch(_CYCLE) as sub:
            call_command("edge_sync_cycle", slug="gilead", operator_base="https://op.example")
        self.assertEqual(sub.call_count, 2, sub.call_args_list)
        self.assertEqual(sub.call_args_list[0].args[0], "post_edge_outbox")
        self.assertEqual(sub.call_args_list[1].args[0], "pull_edge_inbox")
