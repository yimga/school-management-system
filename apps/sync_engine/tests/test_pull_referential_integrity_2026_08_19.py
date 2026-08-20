"""Cloud->box pulls died whole on a child whose parent the box had never been given.

Reported from production:

    pull failed: insert or update on table "academics_specialty" violates foreign key
    constraint "academics_specialty_department_id_e1b16347_fk_academics"
    DETAIL: Key (department_id)=(2) is not present in table "academics_department".

Three separate defects stacked into one permanent wedge.

1. THE ROOT CAUSE — cloud->box had no create path at all.
   ``client_offline_id`` marks a row created OFFLINE ON A BOX, so a row authored on the
   CLOUD carries an empty one and ``apply_pulled_bundle`` routes it to the update-by-pk
   path. That path answered 404 for a pk the box had never seen and moved on. Every record
   created on the cloud AFTER a box was cloned was therefore permanently invisible to that
   box — departments, subjects, specialties, terms — with no error anywhere. The box simply
   diverged, and then failed on the first child row referencing one of the parents it had
   never been given.

2. THE AMPLIFIER — the per-row savepoint could not do its job on PostgreSQL.
   ``_apply_changes_inner`` wraps each row in a savepoint and catches ``IntegrityError``
   specifically so that "a FK to a deleted parent" degrades that ONE row. Django creates
   every foreign key on PostgreSQL as DEFERRABLE INITIALLY DEFERRED, so the violation is
   not raised by ``save()`` — it is raised by the COMMIT of the outermost transaction, by
   which point the savepoint has long been released. The error escaped ``apply_changes``
   entirely, rolled back every good row alongside the bad one, and surfaced as a
   cycle-level ``pull failed``. SQLite checks foreign keys immediately, which is exactly
   why the whole suite was green while production was wedged.

3. THE RATCHET — a failed apply leaves the pull cursor where it was, so the next cycle
   re-downloads the identical bundle with the identical poison row. Forever.

Bundle order made it likelier still: rows are sorted by ``updated_at`` because that is what
makes a page boundary a safe cursor, and ``updated_at`` order says nothing about dependency,
so a child could be applied ahead of a parent sitting later in the very same bundle.
"""
from __future__ import annotations

import datetime as dt
from unittest import mock

from django.test import TestCase

from apps.academics.models import AcademicYear, Department, Specialty
from apps.accounts.models import User
from apps.api.sync_services import (
    _force_immediate_constraints,
    _unresolvable_fk,
    apply_changes,
)
from apps.schools.models import School
from apps.sync_engine.models import SyncApplyLedger


def _row(entity_type, pk, changes, *, updated_at="2026-08-19T10:00:00+00:00"):
    """A bundle row exactly as the operator's download endpoint emits it: no
    ``client_offline_id``, because the row was authored on the CLOUD."""
    return {
        "entity_type": entity_type,
        "id": pk,
        "client_offline_id": "",
        "changes": changes,
        "updated_at": updated_at,
    }


class _Fixture(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Ref School", slug="ref-school", subdomain="ref-school"
        )
        self.admin = User.objects.create_user(
            username="ref-admin", password="x" * 12, role=User.Role.ADMIN, is_staff=True
        )
        self.dept = Department.objects.create(
            school=self.school, name="Existing", code="EXI"
        )
        # A pk that exists on neither side — the "department_id=2" of the report.
        self.ghost_dept_pk = self.dept.pk + 9_000
        self.new_dept_pk = self.dept.pk + 1_000
        self.new_spec_pk = (
            Specialty.objects.order_by("-pk").values_list("pk", flat=True).first() or 0
        ) + 1_000

    def _pull(self, rows, **kw):
        return apply_changes(
            str(self.school.id), self.admin, rows,
            persist_conflicts=False, sync_origin="cloud-pull", **kw,
        )


class CloudAuthoredCreateTests(_Fixture):
    """Defect 1: a record created on the cloud after the clone must reach the box."""

    def test_a_pk_the_box_has_never_seen_is_created_not_skipped(self):
        out = self._pull([_row("department", self.new_dept_pk, {"name": "New", "code": "NEW"})])

        self.assertEqual(out["results"][0]["status"], 201)
        created = Department.objects.get(pk=self.new_dept_pk)
        self.assertEqual(created.name, "New")
        # The operator's pk is PRESERVED. That is the whole basis for creating by pk here:
        # the clone is pk-stable, so both sides address the row the same way afterwards.
        self.assertEqual(created.pk, self.new_dept_pk)

    def test_the_created_row_is_bound_to_the_pulling_school(self):
        self._pull([_row("department", self.new_dept_pk, {"name": "New", "code": "NEW"})])
        self.assertEqual(
            Department.objects.get(pk=self.new_dept_pk).school_id, self.school.id
        )

    def test_the_create_records_echo_suppression_provenance(self):
        """Without provenance the box pushes the row it just received straight back up."""
        self._pull([_row("department", self.new_dept_pk, {"name": "New", "code": "NEW"})])
        ledger = SyncApplyLedger.objects.get(
            school=self.school, entity_type="department", local_pk=str(self.new_dept_pk)
        )
        self.assertEqual(ledger.origin, "cloud-pull")

    def test_a_box_push_may_still_not_mint_a_pk_on_the_operator(self):
        """Create-by-pk is correct DOWNWARD only. Upward it would be a pk collision and an
        authority inversion, so the 404 has to stay for every other caller."""
        out = apply_changes(
            str(self.school.id), self.admin,
            [_row("department", self.new_dept_pk, {"name": "New", "code": "NEW"})],
            persist_conflicts=False, sync_origin="edge-push",
        )
        self.assertEqual(out["results"][0]["status"], 404)
        self.assertFalse(Department.objects.filter(pk=self.new_dept_pk).exists())

    def test_the_online_delta_api_is_unchanged(self):
        """sync_origin=None is the ordinary online DeltaSyncAPI. It must keep 404-ing, so
        no non-edge tenant on a shared deployment sees new behaviour."""
        out = apply_changes(
            str(self.school.id), self.admin,
            [_row("classroom", 987_654, {"name": "Ghost"})],
            persist_conflicts=False,
        )
        self.assertEqual(out["results"][0]["status"], 404)

    def test_an_entity_held_from_creation_is_refused_with_its_reason(self):
        """`teacher` converges as an UPDATE but may never be CREATED across the rail — it
        would require minting an accounts.User, which is an authentication decision. The
        rule is direction-independent, so a pull may not do it either."""
        out = self._pull([_row("teacher", 987_654, {"position_title": "Head"})])
        self.assertEqual(out["results"][0]["status"], 409)
        self.assertEqual(out["results"][0]["data"]["error"], "insert_held_for_entity")


class DependencyOrderTests(_Fixture):
    """A child must not fail on a parent that is sitting later in its own bundle."""

    def test_a_child_listed_before_its_parent_still_lands(self):
        rows = [
            _row("specialty", self.new_spec_pk,
                 {"name": "Plumbing", "code": "PLB", "department_id": self.new_dept_pk}),
            _row("department", self.new_dept_pk, {"name": "Trades", "code": "TRD"}),
        ]
        out = self._pull(rows)

        self.assertEqual([r["status"] for r in out["results"]], [201, 201])
        self.assertEqual(
            Specialty.objects.get(pk=self.new_spec_pk).department_id, self.new_dept_pk
        )

    def test_results_come_back_in_the_callers_order(self):
        """Processing order changed; the response contract did not."""
        rows = [
            _row("specialty", self.new_spec_pk,
                 {"name": "Plumbing", "code": "PLB", "department_id": self.new_dept_pk}),
            _row("department", self.new_dept_pk, {"name": "Trades", "code": "TRD"}),
        ]
        out = self._pull(rows)
        self.assertEqual([r["index"] for r in out["results"]], [0, 1])


class UnresolvableParentTests(_Fixture):
    """Defect 2: one un-appliable row must cost exactly one row."""

    def _hostile_bundle(self):
        return [
            _row("specialty", self.new_spec_pk + 1,
                 {"name": "Orphan", "code": "ORP", "department_id": self.ghost_dept_pk}),
            _row("department", self.new_dept_pk, {"name": "Good", "code": "GUD"}),
        ]

    def test_the_bad_row_is_reported_precisely(self):
        out = self._pull(self._hostile_bundle())
        bad = out["results"][0]
        self.assertEqual(bad["status"], 409)
        self.assertEqual(bad["data"]["error"], "missing_reference")
        # Naming the field, the value and the target table is the difference between an
        # operator who can act and an operator staring at a constraint name.
        self.assertEqual(bad["data"]["field"], "department_id")
        self.assertEqual(bad["data"]["referenced_id"], self.ghost_dept_pk)
        self.assertEqual(bad["data"]["references"], "academics.Department")

    def test_the_bad_row_is_not_written(self):
        self._pull(self._hostile_bundle())
        self.assertFalse(Specialty.objects.filter(pk=self.new_spec_pk + 1).exists())

    def test_every_other_row_in_the_bundle_still_lands(self):
        """The regression that mattered: the good row used to be rolled back with the bad
        one, so a single orphan cost the entire cycle."""
        out = self._pull(self._hostile_bundle())
        self.assertEqual(out["results"][1]["status"], 201)
        self.assertTrue(Department.objects.filter(pk=self.new_dept_pk).exists())

    def test_an_update_that_repoints_at_a_missing_parent_is_refused(self):
        """The preflight guards the UPDATE path too, not only creates.

        The row must carry a NEWER timestamp than the server copy, or `_conflict_decision`
        refuses it as a stale LWW conflict first and the preflight is never reached — which
        is correct ordering, and is what the first cut of this test accidentally asserted.
        """
        from django.utils import timezone as tz

        spec = Specialty.objects.create(
            school=self.school, name="Existing", code="EXS", department=self.dept
        )
        newer = (tz.now() + dt.timedelta(minutes=5)).isoformat()
        out = self._pull(
            [_row("specialty", spec.pk, {"department_id": self.ghost_dept_pk},
                  updated_at=newer)]
        )
        self.assertEqual(out["results"][0]["status"], 409)
        self.assertEqual(out["results"][0]["data"]["error"], "missing_reference")
        spec.refresh_from_db()
        self.assertEqual(spec.department_id, self.dept.pk)

    def test_a_null_foreign_key_is_not_treated_as_missing(self):
        year = AcademicYear.objects.create(
            school=self.school, name="2026",
            start_date=dt.date(2026, 9, 1), end_date=dt.date(2027, 6, 30),
        )
        model, allowed = Specialty, {"department_id"}
        self.assertIsNone(_unresolvable_fk(model, allowed, {"department_id": None}))
        self.assertIsNotNone(year.pk)  # fixture sanity

    def test_a_resolvable_parent_passes_the_preflight(self):
        self.assertIsNone(
            _unresolvable_fk(Specialty, {"department_id"}, {"department_id": self.dept.pk})
        )


class DeferredConstraintTests(TestCase):
    """Defect 2's backstop. The preflight covers what we can foresee; this bounds the
    blast radius of what we cannot.

    Django emits every FK on PostgreSQL as DEFERRABLE INITIALLY DEFERRED, so a violation is
    raised by COMMIT rather than by ``save()`` and no savepoint in the apply path can see
    it. Switching the transaction to IMMEDIATE restores the semantics those savepoints were
    written for. There is nothing to assert against SQLite (it already checks immediately),
    so the contract is asserted against the statement we issue.
    """

    def _fake_connection(self, vendor):
        conn = mock.MagicMock()
        conn.vendor = vendor
        return conn

    def test_postgresql_is_switched_to_immediate(self):
        conn = self._fake_connection("postgresql")
        with mock.patch("django.db.connection", conn):
            _force_immediate_constraints()
        conn.cursor.return_value.__enter__.return_value.execute.assert_called_once_with(
            "SET CONSTRAINTS ALL IMMEDIATE"
        )

    def test_other_backends_are_left_alone(self):
        conn = self._fake_connection("sqlite")
        with mock.patch("django.db.connection", conn):
            _force_immediate_constraints()
        conn.cursor.assert_not_called()

    def test_a_failure_to_switch_never_aborts_the_apply(self):
        """Hardening must not become the thing that breaks sync."""
        conn = self._fake_connection("postgresql")
        conn.cursor.side_effect = RuntimeError("connection is having a day")
        with mock.patch("django.db.connection", conn):
            _force_immediate_constraints()  # must not raise

    def test_the_apply_transaction_actually_switches_them(self):
        """Asserting the call site, not just the helper — the helper being correct is
        worthless if nothing invokes it."""
        school = School.objects.create(
            name="Imm School", slug="imm-school", subdomain="imm-school"
        )
        admin = User.objects.create_user(
            username="imm-admin", password="x" * 12, role=User.Role.ADMIN, is_staff=True
        )
        with mock.patch(
            "apps.api.sync_services._force_immediate_constraints"
        ) as switched:
            apply_changes(str(school.id), admin, [], sync_origin="cloud-pull")
        switched.assert_called_once()


class SkippedRowVisibilityTests(_Fixture):
    """Defect 3's companion: a partial pull must not render as a clean one.

    ``pulled`` counts rows RECEIVED, so a bundle in which every row was refused still
    reported "pulled 12" and a green cycle. The count of rows that did NOT land is now
    carried separately, with its reasons, all the way to the Sync Center.
    """

    def _apply_bundle(self, rows):
        from apps.sync_engine import edge_inbox

        with mock.patch.object(
            edge_inbox, "verify_and_parse_bundle", return_value=(rows, [])
        ):
            return edge_inbox.apply_pulled_bundle(
                self.school, self.admin, b"<signed>", origin="cloud-pull"
            )

    def test_a_refused_row_is_counted_and_named(self):
        out = self._apply_bundle([
            _row("specialty", self.new_spec_pk,
                 {"name": "Orphan", "code": "ORP", "department_id": self.ghost_dept_pk}),
            _row("department", self.new_dept_pk, {"name": "Good", "code": "GUD"}),
        ])
        self.assertTrue(out["ok"])
        self.assertEqual(out["received"], 2)
        self.assertEqual(out["skipped"], 1)
        self.assertEqual(out["skipped_reasons"], {"missing_reference": 1})

    def test_a_fully_applied_bundle_reports_nothing_skipped(self):
        out = self._apply_bundle(
            [_row("department", self.new_dept_pk, {"name": "Good", "code": "GUD"})]
        )
        self.assertEqual(out["skipped"], 0)
        self.assertEqual(out["skipped_reasons"], {})

    def test_a_conflict_is_not_double_counted_as_skipped(self):
        """A conflict already has its own surface and its own operator workflow. Counting
        it as 'not applied' as well would inflate the number that is supposed to mean
        'nobody is looking at this'."""
        spec = Specialty.objects.create(
            school=self.school, name="Existing", code="EXS", department=self.dept
        )
        from apps.sync_engine import edge_inbox

        rows = [_row("specialty", spec.pk, {"name": "Renamed"},
                     updated_at="2000-01-01T00:00:00+00:00")]
        with mock.patch.object(
            edge_inbox, "verify_and_parse_bundle", return_value=(rows, [])
        ), mock.patch(
            "apps.api.sync_services._conflict_decision", return_value="conflict"
        ):
            out = edge_inbox.apply_pulled_bundle(
                self.school, self.admin, b"<signed>", origin="cloud-pull"
            )
        self.assertEqual(out["conflicts"], 1)
        self.assertEqual(out["skipped"], 0)


class MissingParentSelfHealTests(_Fixture):
    """Refusing the row cleanly stops the wedge; it does not make the data converge.

    A ``missing_reference`` means the parent's own ``updated_at`` is older than the pull
    cursor, so the incremental delta will never offer it again — the child would be refused
    on every future cycle and the two sides would stay quietly divergent, which is the
    failure mode this whole change exists to end. Rewinding the pull cursor makes the next
    cycle replay the corpus, which DOES contain the parent.
    """

    def setUp(self):
        super().setUp()
        from django.core.cache import cache

        cache.clear()

    def _cursor(self):
        from apps.sync_engine.models import EdgeSyncCursor, get_sync_cursor

        return get_sync_cursor(self.school, EdgeSyncCursor.PULL)

    def _seed_cursor(self):
        from django.utils import timezone as tz

        from apps.sync_engine.models import EdgeSyncCursor, set_sync_cursor

        set_sync_cursor(self.school, EdgeSyncCursor.PULL, tz.now())
        self.assertIsNotNone(self._cursor())

    def test_a_missing_parent_rewinds_the_pull_cursor(self):
        from apps.sync_engine.sync_runner import _request_replay_for_missing_parents

        self._seed_cursor()
        note = _request_replay_for_missing_parents(self.school)
        self.assertIsNone(self._cursor(), "the next cycle must replay the whole corpus")
        self.assertIn("replays the full corpus", note)

    def test_a_second_request_is_refused_until_the_cooldown_expires(self):
        """A replay is expensive, and a reference a replay CANNOT satisfy would otherwise
        rewind the cursor on every single cycle, forever."""
        from apps.sync_engine.sync_runner import _request_replay_for_missing_parents

        _request_replay_for_missing_parents(self.school)
        self._seed_cursor()
        note = _request_replay_for_missing_parents(self.school)
        self.assertIsNotNone(self._cursor(), "the cooldown did not hold the second rewind")
        self.assertIn("did not request another", note)

    def test_the_cooldown_is_per_school(self):
        from apps.sync_engine.sync_runner import _request_replay_for_missing_parents

        other = School.objects.create(
            name="Other", slug="other-school", subdomain="other-school"
        )
        _request_replay_for_missing_parents(self.school)
        note = _request_replay_for_missing_parents(other)
        self.assertIn("replays the full corpus", note)

    def test_a_failure_to_heal_never_breaks_the_cycle(self):
        from apps.sync_engine import sync_runner

        with mock.patch(
            "apps.sync_engine.models.reset_sync_cursors",
            side_effect=RuntimeError("db went away"),
        ):
            note = sync_runner._request_replay_for_missing_parents(self.school)
        self.assertIn("could not request a replay", note)

    def test_the_runner_asks_for_a_replay_when_a_parent_is_missing(self):
        """The wiring, not just the helper: a cycle whose apply reported a missing parent
        must leave the cursor rewound."""
        from django.test import override_settings

        from apps.sync_engine import edge_inbox, edge_outbox, sync_runner

        User.objects.create_superuser(
            username="heal-super", password="x" * 12, email="heal@test.com"
        )
        self._seed_cursor()

        empty_delta = ([], {"row_count": 0, "counts": {}, "high_water": None,
                            "high_water_iso": None})
        applied = {
            "ok": True, "received": 2, "malformed": 0, "applied": 1, "conflicts": 0,
            "created": 1, "upserted": 0, "skipped": 1,
            "skipped_reasons": {"missing_reference": 1},
            "conflict_details": [], "results": [], "insert_results": [],
        }
        with override_settings(
            RMC_EDGE_SYNC_ENABLED=True, RMC_EDGE_OPERATOR_BASE="https://ops.test"
        ), mock.patch.object(
            edge_outbox, "build_edge_delta_rows", return_value=empty_delta
        ), mock.patch.object(
            edge_outbox, "pull_bundle", return_value=(200, b"", None)
        ), mock.patch.object(
            edge_inbox, "apply_pulled_bundle", return_value=applied
        ):
            result = sync_runner.run_sync_cycle(self.school, mode="live")

        self.assertEqual(result["skipped"], 1, "the cycle must carry the skipped count")
        self.assertIn("NOT applied", result["message"])
        self.assertIsNone(self._cursor(), "the runner did not request a replay")


class CreatePathGateTests(_Fixture):
    """A create is a WRITE, so it answers to the same gates every other inbound write does.

    Skipping them because there is no existing row to compare against would have made the
    new create path the way AROUND them — the same shape of hole the down-only policy had
    on the insert path (test_edge_sync_down_only_insert_path_2026_08_17).
    """

    def test_a_non_admin_principal_may_not_create(self):
        """Same bar as apply_edge_inserts: the box acts as a bound school admin."""
        student = User.objects.create_user(
            username="ref-student", password="x" * 12, role=User.Role.STUDENT
        )
        out = apply_changes(
            str(self.school.id), student,
            [_row("department", self.new_dept_pk, {"name": "New", "code": "NEW"})],
            persist_conflicts=False, sync_origin="cloud-pull",
        )
        self.assertEqual(out["results"][0]["status"], 403)
        self.assertFalse(Department.objects.filter(pk=self.new_dept_pk).exists())

    def test_an_online_required_domain_is_never_created_by_a_pull(self):
        """`ONLINE_REQUIRED` (credentials, lifecycle, payment settlement) is never applied
        through the offline/sync path. That has to hold whether the row already exists or
        not — otherwise 'it does not exist yet' becomes the bypass."""
        with mock.patch(
            "apps.api.sync_services._conflict_decision", return_value="reject"
        ):
            out = self._pull(
                [_row("department", self.new_dept_pk, {"name": "New", "code": "NEW"})]
            )
        self.assertEqual(out["results"][0]["status"], 409)
        self.assertEqual(out["results"][0]["data"]["error"], "online_required")
        self.assertFalse(Department.objects.filter(pk=self.new_dept_pk).exists())

    def test_a_row_the_local_schema_cannot_satisfy_is_reported_not_raised(self):
        """A constraint the incoming row cannot satisfy — here the per-school unique
        `code` (migration academics.0076), which is what a divergent box actually hits when
        the same code was reused under a different pk. It must degrade to ONE reported row,
        never take down the pull."""
        out = self._pull(
            [_row("department", self.new_dept_pk, {"name": "Clash", "code": self.dept.code})]
        )
        self.assertEqual(out["results"][0]["status"], 422)
        self.assertEqual(out["results"][0]["data"]["error"], "create_failed")
        self.assertFalse(Department.objects.filter(pk=self.new_dept_pk).exists())

    def test_a_failed_create_does_not_stop_the_rest_of_the_bundle(self):
        out = self._pull([
            _row("department", self.new_dept_pk, {"name": "Clash", "code": self.dept.code}),
            _row("department", self.new_dept_pk + 1, {"name": "Fine", "code": "FIN"}),
        ])
        self.assertEqual(out["results"][0]["status"], 422)
        self.assertEqual(out["results"][1]["status"], 201)
        self.assertTrue(Department.objects.filter(pk=self.new_dept_pk + 1).exists())


class PreflightRobustnessTests(_Fixture):
    """The preflight must never become the crash it exists to prevent.

    It runs OUTSIDE the per-row savepoint (it has to — its whole purpose is to decide
    before the write), so anything it raises escapes `apply_changes` and takes the bundle
    down exactly the way the original bug did. A pk column that cannot even parse the
    incoming value raises ValueError/ValidationError from the lookup itself.
    """

    def test_an_unparseable_reference_is_reported_not_raised(self):
        out = self._pull([
            _row("specialty", self.new_spec_pk,
                 {"name": "Bad", "code": "BAD", "department_id": "not-an-integer"}),
            _row("department", self.new_dept_pk, {"name": "Fine", "code": "FIN"}),
        ])
        self.assertEqual(out["results"][0]["status"], 409)
        self.assertEqual(out["results"][0]["data"]["error"], "missing_reference")
        self.assertEqual(out["results"][1]["status"], 201, "the bundle must still land")

    def test_a_broken_target_model_degrades_to_no_finding(self):
        """If the FK graph itself cannot be derived, the row proceeds to the ordinary
        write path (and its savepoint) rather than the whole apply dying here."""
        with mock.patch(
            "apps.api.sync_services._fk_reference_targets",
            side_effect=RuntimeError("meta exploded"),
        ):
            self.assertIsNone(
                _unresolvable_fk(Specialty, {"department_id"}, {"department_id": 1})
            )

    def test_an_insert_result_is_not_masked_by_an_update_conflict_index(self):
        """The two result lists index INDEPENDENTLY — one enumerates the update rows, the
        other the insert rows — so matching a conflict index against both would silently
        swallow a refused insert that happened to share an index with a conflict."""
        from apps.sync_engine import edge_inbox

        out = {
            "success_count": 0,
            "results": [{"index": 0, "status": 409, "data": {"error": "conflict"}}],
            "conflicts": [{"index": 0}],
        }
        inserted = {
            "created": 0, "updated": 0,
            "results": [{"index": 0, "status": 409,
                         "data": {"error": "missing_reference"}}],
        }
        with mock.patch.object(
            edge_inbox,
            "verify_and_parse_bundle",
            # One row WITHOUT a client_offline_id (routed to apply_changes) and one WITH
            # (routed to apply_edge_inserts) — otherwise the insert path is never called
            # and the test would pass without exercising anything.
            return_value=([{}, {"client_offline_id": "box-made-this"}], []),
        ), mock.patch(
            "apps.api.sync_services.apply_changes", return_value=out
        ), mock.patch(
            "apps.api.sync_services.apply_edge_inserts", return_value=inserted
        ):
            res = edge_inbox.apply_pulled_bundle(
                self.school, self.admin, b"<signed>", origin="cloud-pull"
            )
        self.assertEqual(res["conflicts"], 1)
        self.assertEqual(res["skipped"], 1, "the refused INSERT was swallowed")
        self.assertEqual(res["skipped_reasons"], {"missing_reference": 1})
