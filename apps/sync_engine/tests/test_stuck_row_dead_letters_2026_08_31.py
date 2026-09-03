"""A row the sync rail keeps refusing must be FINDABLE, CLEARABLE and LOUD.

THE INCIDENT THESE TESTS ENCODE. On one box, 39 teacher rows were refused on ALL 687
sync cycles of a single day - 26,598 "not applied" - and no alarm ever fired. Diagnosing
it took a human several days. Three separate defects made that possible, and each one is
driven here through the REAL apply path rather than asserted about in the abstract:

  1. a refused row was counted into ``EdgeSyncRun.skipped`` and DISCARDED. No per-row
     record, no attempt counter, no first-seen age. ``SyncFileTransfer`` had carried an
     ``attempts`` counter for files the whole time; rows got nothing;
  2. a skip creates no ``SyncConflict``, so the row was not even in the one store an
     operator screen reads;
  3. ``sync_health._collect_delta`` reads ONLY pending ``SyncConflict`` rows, so
     ``EdgeSyncRun.skipped`` could never reach ``evaluate_backlog_incidents`` and NO
     ``PlatformIncident`` could open for a stalled box.

The headline test reproduces the incident's SHAPE - the same rows refused on many
consecutive cycles - and then asks the question the operator could not answer: which
records, why, and for how long. Against the code before this wave it fails at the first
assertion about records, because nothing recorded any.

The refusal used throughout is the real one: ``insert_held_for_entity`` for ``teacher``.
A teacher record requires an ``accounts.User``, and the rail may not provision a login in
either direction, so no resync will ever make those rows land - which is exactly why they
were still being refused 687 cycles later.

SQLite is what runs here, and it does not prove Postgres: FK constraints are immediate on
SQLite and DEFERRABLE INITIALLY DEFERRED on Postgres. What these tests DO prove is that
the recording happens outside the apply transaction and takes its own savepoint, which is
the property that makes the difference on either backend.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from unittest import mock

from django.db.models import Sum
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import Department, Specialty
from apps.accounts.models import Permission as FeaturePermission, User
from apps.api.sync_services import (
    _get_entity_config,
    apply_changes,
    apply_edge_inserts,
)
from apps.observability.models import PlatformIncident
from apps.observability.sync_health import collect_sync_health, evaluate_backlog_incidents
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.models import (
    EdgeSyncRun,
    SyncDeadLetter,
    dead_letter_summary,
    open_dead_letters,
    record_dead_letter,
)


def _row(entity_type, pk, changes, *, updated_at="2026-08-31T10:00:00+00:00"):
    """A bundle row exactly as the operator's download endpoint emits it."""
    return {
        "entity_type": entity_type,
        "id": pk,
        "client_offline_id": "",
        "changes": changes,
        "updated_at": updated_at,
    }


class _Fixture(TestCase):
    # setUpTestData, not setUp: creating a School fires the tenant provisioning signals
    # (permission catalog, schema guard, defaults), which costs seconds. Doing it once
    # per CLASS instead of once per test is the difference between a suite that runs and
    # one nobody waits for; TestCase still rolls every test back to this state.
    @classmethod
    def setUpTestData(cls):
        uid = uuid.uuid4().hex[:8]
        cls.school = School.objects.create(
            name=f"Stuck {uid}", slug=f"stuck-{uid}", subdomain=f"stuck{uid}"
        )
        cls.admin = User.objects.create_user(
            username=f"stuck-admin-{uid}",
            password="x" * 12,
            role=User.Role.ADMIN,
            is_staff=True,
        )
        cls.dept = Department.objects.create(
            school=cls.school, name="Existing", code=f"E{uid[:3].upper()}"
        )
        cls.ghost_dept_pk = cls.dept.pk + 9_000
        cls.new_spec_pk = (
            Specialty.objects.order_by("-pk").values_list("pk", flat=True).first() or 0
        ) + 1_000
        # A block of teacher pks this box has never seen - the incident's own shape.
        cls.teacher_base_pk = 900_000

    def _pull(self, rows, **kw):
        return apply_changes(
            str(self.school.id),
            self.admin,
            rows,
            persist_conflicts=False,
            sync_origin="cloud-pull",
            **kw,
        )

    def _teacher_rows(self, count):
        """``count`` teacher rows the box has never seen, each with one settable field."""
        _model, allowed = _get_entity_config(include_derived=True)["teacher"]
        field = next(
            (f for f in ("position_title", "qualification", "specialization") if f in allowed),
            sorted(allowed)[0],
        )
        return [
            _row("teacher", self.teacher_base_pk + i, {field: f"Held {i}"})
            for i in range(count)
        ]


# --------------------------------------------------------------------------- #
# 1. The incident, reproduced: the SAME rows refused on many consecutive cycles
# --------------------------------------------------------------------------- #
class SameRowsRefusedEveryCycleTests(_Fixture):
    """39 rows x 20 cycles. The old surface says 780; an operator needs 39."""

    ROWS = 39
    CYCLES = 20

    def _run_the_day(self):
        rows = self._teacher_rows(self.ROWS)
        for _ in range(self.CYCLES):
            out = self._pull(rows)
            refused = [r for r in out["results"] if r["status"] not in (200, 201)]
            self.assertEqual(len(refused), self.ROWS)
            self.assertEqual(refused[0]["data"]["error"], "insert_held_for_entity")
            # What the runner records for the cycle: a COUNT, exactly as it always has.
            EdgeSyncRun.record(
                self.school, mode="live", ok=True, pulled=self.ROWS, skipped=len(refused)
            )
        return rows

    def test_an_operator_can_name_the_stuck_records_after_a_day_of_cycles(self):
        self._run_the_day()

        # (a) The surface that already existed. It is a SUM OVER CYCLES and it is honest
        #     about attempts - but 780 is not 780 records, it is 39 records 20 times, and
        #     nothing about the number says so.
        per_cycle_sum = EdgeSyncRun.objects.filter(school=self.school).aggregate(
            s=Sum("skipped")
        )["s"]
        self.assertEqual(per_cycle_sum, self.ROWS * self.CYCLES)

        # (b) The surface this wave adds: one durable record per stuck ROW.
        self.assertEqual(open_dead_letters(self.school).count(), self.ROWS)

        summary = dead_letter_summary(self.school, limit=self.ROWS)
        self.assertEqual(summary["count"], self.ROWS)
        # Both numbers, side by side, so neither can be read as the other.
        self.assertEqual(summary["attempts_total"], self.ROWS * self.CYCLES)

        # (c) Every question the human had to answer by hand is answerable now.
        self.assertEqual(len(summary["rows"]), self.ROWS)
        for row in summary["rows"]:
            self.assertEqual(row["entity_type"], "teacher")
            self.assertEqual(row["reason"], "insert_held_for_entity")
            self.assertEqual(row["attempts"], self.CYCLES)
            self.assertEqual(row["origin"], "cloud-pull")
            self.assertIsNotNone(row["local_pk"])
            self.assertIsNotNone(row["age_seconds"])
            # The refusal's own explanation travels with it, so "why" needs no lookup.
            self.assertIn("authentication decision", row["detail"])

        self.assertEqual(summary["by_reason"], [{"reason": "insert_held_for_entity", "count": 39}])
        self.assertIsNotNone(summary["oldest_age_seconds"])

    def test_the_record_count_does_not_grow_with_cycles(self):
        """The whole point: 687 cycles must not mean 687x the storage or the noise."""
        rows = self._teacher_rows(3)
        self._pull(rows)
        after_one = SyncDeadLetter.objects.filter(school=self.school).count()
        for _ in range(15):
            self._pull(rows)
        after_sixteen = SyncDeadLetter.objects.filter(school=self.school).count()
        self.assertEqual(after_one, 3)
        self.assertEqual(after_sixteen, 3)
        self.assertEqual(
            sorted(
                SyncDeadLetter.objects.filter(school=self.school).values_list(
                    "attempts", flat=True
                )
            ),
            [16, 16, 16],
        )

    def test_first_seen_at_is_the_start_of_the_stall_not_the_last_cycle(self):
        rows = self._teacher_rows(1)
        self._pull(rows)
        first = SyncDeadLetter.objects.get(school=self.school)
        original_first_seen = first.first_seen_at
        self._pull(rows)
        first.refresh_from_db()
        self.assertEqual(first.first_seen_at, original_first_seen)
        self.assertGreaterEqual(first.last_seen_at, original_first_seen)


# --------------------------------------------------------------------------- #
# 2. A dead letter that outlives its own resolution is a ghost
# --------------------------------------------------------------------------- #
class ClearedWhenTheRowFinallyAppliesTests(_Fixture):
    def _specialty_row(self, department_pk):
        return _row(
            "specialty",
            self.new_spec_pk,
            {"name": "Plumbing", "code": "PLB", "department_id": department_pk},
        )

    def test_a_missing_parent_is_recorded_then_cleared_when_the_parent_arrives(self):
        # Cycle 1..3 - the parent is not there, so the row is refused every time.
        for _ in range(3):
            out = self._pull([self._specialty_row(self.ghost_dept_pk)])
            self.assertEqual(out["results"][0]["data"]["error"], "missing_reference")

        stuck = SyncDeadLetter.objects.get(
            school=self.school, entity_type="specialty", reason="missing_reference"
        )
        self.assertEqual(stuck.attempts, 3)
        self.assertIsNone(stuck.resolved_at)
        self.assertEqual(open_dead_letters(self.school).count(), 1)

        # Cycle 4 - the parent arrives on a later pull, exactly as the rail intends, and
        # the child lands with it.
        out = self._pull(
            [
                self._specialty_row(self.ghost_dept_pk),
                _row("department", self.ghost_dept_pk, {"name": "Trades", "code": "TRD"}),
            ]
        )
        self.assertEqual([r["status"] for r in out["results"]], [201, 201])

        stuck.refresh_from_db()
        self.assertIsNotNone(stuck.resolved_at)
        self.assertEqual(open_dead_letters(self.school).count(), 0)
        self.assertEqual(dead_letter_summary(self.school)["count"], 0)
        self.assertIsNone(dead_letter_summary(self.school)["oldest_age_seconds"])

    def test_clearing_closes_every_reason_for_the_row_not_only_the_last_one(self):
        """The row landed. Nothing about it is stuck, whatever it was stuck on before."""
        record_dead_letter(
            self.school.id, "specialty", self.new_spec_pk, "missing_reference",
            origin="cloud-pull",
        )
        record_dead_letter(
            self.school.id, "specialty", self.new_spec_pk, "apply_failed",
            origin="cloud-pull",
        )
        self.assertEqual(open_dead_letters(self.school).count(), 2)

        Department.objects.create(school=self.school, pk=self.ghost_dept_pk, name="T", code="TT")
        out = self._pull([self._specialty_row(self.ghost_dept_pk)])
        self.assertEqual(out["results"][0]["status"], 201)
        self.assertEqual(open_dead_letters(self.school).count(), 0)
        # Cleared, not deleted: the forensic record survives.
        self.assertEqual(
            SyncDeadLetter.objects.filter(school=self.school, entity_type="specialty").count(), 2
        )

    def test_a_row_that_stalls_again_reopens_with_its_clock_restarted(self):
        """An age alarm must not fire on a stall that ended weeks ago."""
        record_dead_letter(self.school.id, "teacher", 4242, "insert_held_for_entity")
        row = SyncDeadLetter.objects.get(school=self.school, local_pk="4242")
        stale = timezone.now() - timedelta(days=30)
        SyncDeadLetter.objects.filter(pk=row.pk).update(
            first_seen_at=stale, last_seen_at=stale, attempts=500, resolved_at=stale
        )

        record_dead_letter(self.school.id, "teacher", 4242, "insert_held_for_entity")

        row.refresh_from_db()
        self.assertIsNone(row.resolved_at)
        self.assertEqual(row.attempts, 1)
        self.assertGreater(row.first_seen_at, stale)
        self.assertLess(
            dead_letter_summary(self.school)["oldest_age_seconds"], 60
        )


# --------------------------------------------------------------------------- #
# 3. Recording must never be able to break a sync cycle
# --------------------------------------------------------------------------- #
class RecordingCannotBreakACycleTests(_Fixture):
    def test_a_failing_dead_letter_write_does_not_fail_the_apply(self):
        good = _row("department", self.dept.pk + 5_000, {"name": "New", "code": "NW1"})
        bad = self._teacher_rows(1)[0]
        with mock.patch(
            "apps.sync_engine.models.record_dead_letter", side_effect=RuntimeError("boom")
        ):
            out = self._pull([good, bad])
        # The bundle applied exactly as it would have without any of this.
        self.assertEqual([r["status"] for r in out["results"]], [201, 409])
        self.assertTrue(Department.objects.filter(pk=self.dept.pk + 5_000).exists())

    def test_record_dead_letter_swallows_a_database_failure_and_reports_it(self):
        with mock.patch(
            "apps.sync_engine.models.SyncDeadLetter.objects"
        ) as objects:
            objects.filter.side_effect = RuntimeError("no such table")
            self.assertFalse(
                record_dead_letter(self.school.id, "teacher", 1, "insert_held_for_entity")
            )

    def test_a_row_with_nothing_to_key_on_is_not_recorded(self):
        self.assertFalse(record_dead_letter(self.school.id, "teacher", None, "x"))
        self.assertFalse(record_dead_letter(self.school.id, "teacher", "", "x"))
        self.assertFalse(record_dead_letter(None, "teacher", 1, "x"))
        self.assertEqual(SyncDeadLetter.objects.count(), 0)


# --------------------------------------------------------------------------- #
# 4. Scope: only the sync rail, and never a row a human is already being asked about
# --------------------------------------------------------------------------- #
class WhatIsAndIsNotADeadLetterTests(_Fixture):
    def test_an_online_delta_apply_records_nothing(self):
        """sync_origin=None is the ordinary online DeltaSyncAPI - a live request whose
        404 the caller is holding, not a row silently stuck on a rail nobody watches."""
        out = apply_changes(
            str(self.school.id),
            self.admin,
            [_row("classroom", 987_654, {"name": "Ghost"})],
            persist_conflicts=False,
        )
        self.assertEqual(out["results"][0]["status"], 404)
        self.assertEqual(SyncDeadLetter.objects.count(), 0)

    def test_a_persisted_conflict_is_not_also_a_dead_letter(self):
        """SyncConflict already has a durable store AND a screen with buttons on it.
        Recording it twice would make the stuck-row list mostly conflicts."""
        from apps.siteconfig.models import SyncConflict

        self.dept.name = "Locally edited"
        self.dept.save()
        out = apply_changes(
            str(self.school.id),
            self.admin,
            [
                _row(
                    "department",
                    self.dept.pk,
                    {"name": "Cloud says otherwise"},
                    updated_at="2020-01-01T00:00:00+00:00",
                )
            ],
            persist_conflicts=True,
            sync_origin="edge-push",
        )
        self.assertEqual(out["results"][0]["data"]["error"], "conflict")
        self.assertEqual(SyncConflict.objects.filter(school=self.school).count(), 1)
        self.assertEqual(SyncDeadLetter.objects.count(), 0)

    def test_an_insert_rail_refusal_is_keyed_on_the_offline_anchor(self):
        """An insert row carries the BOX's local pk, which is reassigned on arrival and
        cannot identify the same row across two cycles. The anchor can."""
        anchor = "offline-anchor-abc123"
        rows = [
            {
                "entity_type": "teacher",
                "id": 7,
                "client_offline_id": anchor,
                "changes": {"position_title": "Head"},
                "updated_at": "2026-08-31T10:00:00+00:00",
            }
        ]
        for _ in range(4):
            out = apply_edge_inserts(
                str(self.school.id), self.admin, rows, sync_origin="edge-push"
            )
            self.assertEqual(out["results"][0]["data"]["error"], "insert_held_for_entity")

        row = SyncDeadLetter.objects.get(school=self.school, entity_type="teacher")
        self.assertEqual(row.local_pk, anchor)
        self.assertEqual(row.client_offline_id, anchor)
        self.assertEqual(row.attempts, 4)
        self.assertEqual(row.origin, "edge-push")


# --------------------------------------------------------------------------- #
# 5. It must ALERT - and on AGE, not only on depth
# --------------------------------------------------------------------------- #
class EdgeRailReachesTheIncidentEvaluatorTests(_Fixture):
    def _stall(self, *, rows, age):
        """``rows`` stuck rows whose oldest first_seen_at is ``age`` old."""
        moment = timezone.now() - age
        for i in range(rows):
            record_dead_letter(
                self.school.id, "teacher", 500_000 + i, "insert_held_for_entity"
            )
        SyncDeadLetter.objects.filter(school=self.school).update(first_seen_at=moment)

    def test_the_snapshot_carries_the_edge_rail_at_all(self):
        """_collect_delta reads only pending SyncConflict rows, so before this the edge
        rail had no number in the snapshot for any threshold to be applied to."""
        self._stall(rows=3, age=timedelta(hours=2))
        snapshot = collect_sync_health(redis_client=None)
        self.assertIn("edge", snapshot)
        self.assertTrue(snapshot["edge"]["available"])
        self.assertEqual(snapshot["edge"]["stuck_rows"], 3)
        self.assertEqual(snapshot["edge"]["schools_affected"], 1)
        self.assertGreater(snapshot["edge"]["oldest_stuck_age_seconds"], 3600)

    @override_settings(
        RMC_SYNC_EDGE_STUCK_ROWS_MAX=1000,  # depth is deliberately unreachable
        RMC_SYNC_EDGE_STUCK_AGE_MAX_SECONDS=3600,
    )
    def test_an_incident_opens_on_the_OLDEST_ROW_AGE_even_when_depth_is_tiny(self):
        """The failure that actually happened: a permanent backlog sits at a CONSTANT
        depth, so a depth threshold it has not already crossed it never will."""
        self._stall(rows=2, age=timedelta(hours=14))
        outcome = evaluate_backlog_incidents(redis_client=None)

        self.assertIn("edge_stuck_age", outcome["opened"])
        self.assertNotIn("edge_stuck_rows", outcome["opened"])
        incident = PlatformIncident.objects.get(
            source_system="sync_health", details__incident_key="sync_backlog_edge_stuck_age"
        )
        self.assertEqual(incident.status, PlatformIncident.Status.OPEN)
        self.assertEqual(incident.details.get("unit"), "seconds")

    @override_settings(
        RMC_SYNC_EDGE_STUCK_ROWS_MAX=1000, RMC_SYNC_EDGE_STUCK_AGE_MAX_SECONDS=3600
    )
    def test_a_young_stall_opens_nothing_so_a_normal_late_parent_is_not_an_alarm(self):
        self._stall(rows=40, age=timedelta(minutes=2))
        outcome = evaluate_backlog_incidents(redis_client=None)
        self.assertNotIn("edge_stuck_age", outcome["opened"])
        self.assertFalse(
            PlatformIncident.objects.filter(
                source_system="sync_health",
                details__incident_key="sync_backlog_edge_stuck_age",
                status=PlatformIncident.Status.OPEN,
            ).exists()
        )

    @override_settings(
        RMC_SYNC_EDGE_STUCK_ROWS_MAX=1, RMC_SYNC_EDGE_STUCK_AGE_MAX_SECONDS=86400
    )
    def test_depth_still_has_its_own_rail(self):
        self._stall(rows=5, age=timedelta(minutes=1))
        outcome = evaluate_backlog_incidents(redis_client=None)
        self.assertIn("edge_stuck_rows", outcome["opened"])
        self.assertNotIn("edge_stuck_age", outcome["opened"])

    @override_settings(
        RMC_SYNC_EDGE_STUCK_ROWS_MAX=1000, RMC_SYNC_EDGE_STUCK_AGE_MAX_SECONDS=3600
    )
    def test_recovery_resolves_the_incident(self):
        self._stall(rows=2, age=timedelta(hours=14))
        evaluate_backlog_incidents(redis_client=None)
        SyncDeadLetter.objects.filter(school=self.school).update(
            resolved_at=timezone.now()
        )
        outcome = evaluate_backlog_incidents(redis_client=None)
        self.assertIn("edge_stuck_age", outcome["resolved"])
        incident = PlatformIncident.objects.get(
            source_system="sync_health", details__incident_key="sync_backlog_edge_stuck_age"
        )
        self.assertEqual(incident.status, PlatformIncident.Status.RESOLVED)


# --------------------------------------------------------------------------- #
# 6. It must be SURFACED to a human
# --------------------------------------------------------------------------- #
# The host's first label IS the tenant subdomain — that is how the request resolves to a
# school, so the two are pinned together here rather than randomised.
_T_SUBDOMAIN = "stuck-rows"
_T_HOST = f"{_T_SUBDOMAIN}.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _T_HOST])
class SyncCenterShowsTheRowsNotJustTheSumTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Stuck Rows School",
            slug=_T_SUBDOMAIN,
            subdomain=_T_SUBDOMAIN,
            is_active=True,
        )
        perm, _ = FeaturePermission.objects.get_or_create(
            code="settings.manage", defaults={"name": "Manage settings"}
        )
        cls.admin = User.objects.create_user(
            username="stuck-ui-admin", password="x" * 12, role=User.Role.ADMIN
        )
        cls.admin.feature_permissions.add(perm)
        SchoolMembership.objects.create(
            user=cls.admin, school=cls.school, role=User.Role.ADMIN, is_primary=True
        )
        # 39 rows refused 20 times each: the incident's numbers exactly. Written
        # directly rather than driven through 780 applies — the RECORDING behaviour is
        # proven against the real apply path above; what is under test here is the SCREEN.
        moment = timezone.now()
        SyncDeadLetter.objects.bulk_create(
            [
                SyncDeadLetter(
                    school=cls.school,
                    entity_type="teacher",
                    local_pk=str(700_000 + i),
                    reason="insert_held_for_entity",
                    detail="reason=a teacher record requires an accounts.User",
                    origin="cloud-pull",
                    attempts=20,
                    # Oldest first, all in the past, so the page's "stuck for ..." and
                    # the poll's oldest-age are real numbers rather than zeroes.
                    first_seen_at=moment - timedelta(minutes=39 - i),
                    last_seen_at=moment,
                )
                for i in range(39)
            ]
        )

    def setUp(self):
        self.client = Client(HTTP_HOST=_T_HOST, raise_request_exception=False)
        self.client.login(username="stuck-ui-admin", password="x" * 12)

    def test_the_work_queue_names_the_records_and_says_how_long(self):
        resp = self.client.get(reverse("siteconfig:sync_center"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn("data-rmc-sc-stuck", body)
        # The count of RECORDS, and the count of ATTEMPTS, named apart.
        self.assertIn("39 records cannot be applied", body)
        self.assertIn("refused 780 times in total", body)
        # Entity, pk, reason, attempts - per row, humanized rather than raw tokens.
        self.assertIn("Teacher #700000", body)
        self.assertIn("Insert held for entity", body)
        self.assertIn("20 attempts", body)

    def test_the_status_poll_carries_the_rows_beside_the_per_cycle_sum(self):
        resp = self.client.get(reverse("siteconfig:sync_center_status"))
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["stuck"]["count"], 39)
        self.assertEqual(payload["stuck"]["attempts_total"], 780)
        self.assertEqual(len(payload["stuck"]["rows"]), 25)  # _STUCK_ROW_LIMIT
        self.assertTrue(payload["stuck"]["truncated"])
        self.assertIsNotNone(payload["stuck"]["oldest_age_seconds"])
        self.assertEqual(
            payload["stuck"]["by_reason"][0]["reason"], "insert_held_for_entity"
        )

    def test_a_school_with_nothing_stuck_renders_the_clear_state(self):
        SyncDeadLetter.objects.filter(school=self.school).update(
            resolved_at=timezone.now()
        )
        body = self.client.get(reverse("siteconfig:sync_center")).content.decode("utf-8")
        self.assertNotIn("data-rmc-sc-stuck", body)
        self.assertIn("Nothing needs your attention.", body)
