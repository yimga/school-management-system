"""A roster may only close a conflict it actually answers.

The command exists because the rail cannot break a real tie: ``updated_at`` is ``auto_now``
so the box is always newer, and field-level merge only helps while the two sides touched
different columns. An external roster is evidence rather than a third opinion.

Which makes the dangerous failure mode obvious. Every way of NOT having an answer -- a
blank cell, a column the roster does not have, a key that reaches two lines, a row that
cannot be keyed -- must stay distinguishable from "the roster says X", because each of
them, mistaken for an answer, writes a value nobody chose over a value somebody did. So
most of these tests assert that nothing was written.

The all-or-nothing rule gets its own test for the same reason: settling the fields the
roster knows about and leaving the conflict PENDING would hand a human a row that changed
underneath them, so the diff they were asked to judge is no longer the diff in front of
them.
"""

from __future__ import annotations

import io
import pathlib
import tempfile
import uuid

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase


def _roster(text: str) -> str:
    d = pathlib.Path(tempfile.mkdtemp())
    p = d / "roster.csv"
    p.write_text(text, encoding="utf-8")
    return str(p)


class ReconcileFromSourceTests(TestCase):
    ENTITY = "academic_year"

    def setUp(self):
        from apps.academics.models import AcademicYear
        from apps.schools.models import School

        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Src {uid}", slug=f"src-{uid}", subdomain=f"src{uid}", is_active=True
        )
        self.other = School.objects.create(
            name=f"Oth {uid}", slug=f"oth-{uid}", subdomain=f"oth{uid}", is_active=True
        )
        self.year = AcademicYear.objects.create(
            school=self.school, name="PROVISIONAL",
            start_date="2026-09-01", end_date="2027-07-31",
        )

    # -- helpers ---------------------------------------------------------------

    def _conflict(self, client_data, *, school=None, entity_id=None):
        from apps.siteconfig.models import SyncConflict

        return SyncConflict.objects.create(
            school=school or self.school,
            entity_type=self.ENTITY,
            entity_id=entity_id if entity_id is not None else self.year.pk,
            client_data=client_data,
            status=SyncConflict.Status.PENDING,
        )

    def _run(self, source, *, apply=False, match=None, authoritative=None, school=None, **kw):
        out = io.StringIO()
        call_command(
            "reconcile_sync_conflicts_from_source",
            school=str((school or self.school).pk),
            entity=self.ENTITY,
            source=source,
            match=match or ["Term=start_date:date"],
            authoritative=authoritative or ["Official Name=name"],
            apply=apply,
            stdout=out,
            **kw,
        )
        return out.getvalue()

    def _reread(self):
        self.year.refresh_from_db()
        return self.year

    # -- the roster answers ----------------------------------------------------

    ONE_LINE = "Term,Official Name\n2026-09-01,YEAR 2026/2027\n"

    def test_a_dry_run_writes_nothing(self):
        conflict = self._conflict({"name": "YEAR 2026/2027"})
        text = self._run(_roster(self.ONE_LINE))

        self.assertIn("settled", text)
        self.assertIn("dry run", text)
        self.assertEqual(self._reread().name, "PROVISIONAL")
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, "PENDING")

    def test_apply_writes_the_roster_value_and_closes_the_conflict(self):
        from apps.siteconfig.models import SyncConflict

        conflict = self._conflict({"name": "YEAR 2026/2027"})
        self._run(_roster(self.ONE_LINE), apply=True)

        self.assertEqual(self._reread().name, "YEAR 2026/2027")
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, SyncConflict.Status.RESOLVED_MERGE)
        self.assertIsNotNone(conflict.resolved_at)

    def test_the_resolution_names_its_evidence(self):
        # A row that was overwritten must be able to say which file said so; "someone ran
        # a script once" is not a provenance an operator can audit.
        conflict = self._conflict({"name": "YEAR 2026/2027"})
        self._run(_roster(self.ONE_LINE), apply=True)
        conflict.refresh_from_db()
        self.assertIn("roster.csv", conflict.resolution_note)
        self.assertIn("name", conflict.resolution_note)
        self.assertLessEqual(len(conflict.resolution_note), 255)

    def test_a_row_that_already_matches_is_closed_without_a_write(self):
        self.year.name = "YEAR 2026/2027"
        self.year.save(update_fields=["name"])
        stamp = self._reread().updated_at
        conflict = self._conflict({"name": "SOMETHING ELSE"})

        text = self._run(_roster(self.ONE_LINE), apply=True)
        self.assertIn("already_matches", text)
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, "RESOLVED_MERGE")
        # A needless write would bump auto_now and re-offer the row on the next sync --
        # the exact churn this whole effort exists to stop.
        self.assertEqual(self._reread().updated_at, stamp)

    # -- the roster does NOT answer -------------------------------------------

    def test_a_blank_cell_settles_nothing(self):
        # "nan" is what a pandas export writes for a missing cell.
        conflict = self._conflict({"name": "YEAR 2026/2027"})
        text = self._run(_roster("Term,Official Name\n2026-09-01,nan\n"), apply=True)

        self.assertIn("source_silent", text)
        self.assertEqual(self._reread().name, "PROVISIONAL")
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, "PENDING")

    def test_two_matching_lines_are_ambiguous_not_the_first_one(self):
        conflict = self._conflict({"name": "YEAR 2026/2027"})
        text = self._run(
            _roster("Term,Official Name\n2026-09-01,ONE\n2026-09-01,TWO\n"), apply=True
        )
        self.assertIn("ambiguous_source", text)
        self.assertEqual(self._reread().name, "PROVISIONAL")
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, "PENDING")

    def test_no_matching_line_leaves_it_pending(self):
        conflict = self._conflict({"name": "YEAR 2026/2027"})
        text = self._run(_roster("Term,Official Name\n2099-01-01,ELSEWHERE\n"), apply=True)
        self.assertIn("no_source_row", text)
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, "PENDING")

    def test_settling_some_fields_but_not_all_writes_nothing(self):
        # Handing a human a row that changed underneath them is worse than handing them
        # the whole conflict.
        conflict = self._conflict({"name": "YEAR 2026/2027", "lock_reason": "AUDIT"})
        text = self._run(_roster(self.ONE_LINE), apply=True)

        self.assertIn("partial", text)
        self.assertEqual(self._reread().name, "PROVISIONAL")
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, "PENDING")

    def test_the_same_value_under_different_names_is_reported_as_one_decision(self):
        # The signature of one splitter variant disagreeing with another: the value
        # survives and only its label moves. 32 such rows are 1 decision, not 32.
        self.year.name = "ALPHA"
        self.year.lock_reason = "BETA"
        self.year.save(update_fields=["name", "lock_reason"])
        self._conflict({"name": "BETA", "lock_reason": "ALPHA"})

        text = self._run(
            _roster("Term,Start\n2026-09-01,2026-09-01\n"),
            authoritative=["Start=start_date"],
            apply=True,
        )
        self.assertIn("derived_split", text)
        self.assertIn("ONE decision", text)
        self.assertEqual(self._reread().name, "ALPHA")

    def test_a_split_remainder_counts_even_when_the_roster_settled_the_rest(self):
        """The shape the real backlog has, and the one that inverts the finding.

        A student row differs on the code AND on the name fields. The roster settles the
        code and is silent on the split, so the row is PARTIAL -- but what is left over is
        still the same one convention decision as a row the roster could not help with at
        all. Counting only the rows where the roster settled nothing would report the
        splitter disagreement as a handful of stragglers instead of the single decision it
        is.
        """
        self.year.name = "ALPHA"
        self.year.lock_reason = "BETA"
        self.year.save(update_fields=["name", "lock_reason"])
        self._conflict(
            {"name": "BETA", "lock_reason": "ALPHA", "start_date": "2027-01-15"}
        )

        text = self._run(
            _roster("Ends,Starts\n2027-07-31,2026-09-01\n"),
            match=["Ends=end_date:date"],
            authoritative=["Starts=start_date"],
            apply=True,
        )
        self.assertIn("partial", text)
        self.assertIn("ONE decision", text)
        # and nothing was written, because the row was not settled whole
        self.assertEqual(self._reread().name, "ALPHA")

    # -- the convention, and the fence around it ------------------------------

    def _split_conflict(self):
        """Both sides hold ALPHA and BETA; only the labels differ."""
        self.year.name = "ALPHA"
        self.year.lock_reason = "BETA"
        self.year.save(update_fields=["name", "lock_reason"])
        return self._conflict({"name": "BETA", "lock_reason": "ALPHA"})

    SILENT = "Term,Start\n2026-09-01,2026-09-01\n"

    def _run_silent(self, **kw):
        return self._run(
            _roster(self.SILENT), authoritative=["Start=start_date"], apply=True, **kw
        )

    def test_without_a_convention_it_stays_pending(self):
        # The default needs no decision, so it must not quietly make one.
        conflict = self._split_conflict()
        text = self._run_silent()
        self.assertIn("derived_split", text)
        self.assertIn("--derived-split=keep-local", text)
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, "PENDING")

    def test_keep_local_closes_it_without_writing(self):
        conflict = self._split_conflict()
        stamp = self._reread().updated_at
        text = self._run_silent(derived_split="keep-local")

        self.assertIn("convention_applied", text)
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, "RESOLVED_SERVER")
        self.assertEqual(self._reread().name, "ALPHA")
        # The row already held the decision, so touching it would only bump auto_now
        # and re-offer the row on the next sync.
        self.assertEqual(self._reread().updated_at, stamp)

    def test_keep_incoming_takes_the_clients_decomposition(self):
        conflict = self._split_conflict()
        self._run_silent(derived_split="keep-incoming")

        conflict.refresh_from_db()
        self.assertEqual(conflict.status, "RESOLVED_CLIENT")
        self.assertEqual(self._reread().name, "BETA")
        self.assertEqual(self._reread().lock_reason, "ALPHA")

    def test_the_note_names_the_convention_that_decided_it(self):
        # Months later, "why is this student's surname this way" has to have an answer
        # that distinguishes a register from a policy.
        conflict = self._split_conflict()
        self._run_silent(derived_split="keep-local")
        conflict.refresh_from_db()
        self.assertIn("convention=keep-local", conflict.resolution_note)
        self.assertIn("name", conflict.resolution_note)
        self.assertLessEqual(len(conflict.resolution_note), 255)

    def test_the_convention_never_touches_a_genuine_disagreement(self):
        """THE fence. Two different values with no cross-over are two people editing.

        Without this the flag degenerates into "believe one node", which is the
        timestamp guess wearing a command-line option.
        """
        self.year.name = "ALPHA"
        self.year.lock_reason = "BETA"
        self.year.save(update_fields=["name", "lock_reason"])
        conflict = self._conflict({"name": "GAMMA", "lock_reason": "DELTA"})

        text = self._run_silent(derived_split="keep-local")
        self.assertIn("source_silent", text)
        self.assertNotIn("convention_applied", text)
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, "PENDING")
        self.assertEqual(self._reread().name, "ALPHA")

    def test_a_roster_value_and_a_convention_can_close_one_row_together(self):
        # The real backlog shape: the register settles the code, the convention settles
        # the split, and the row closes as a MERGE because a roster value decided part.
        self.year.name = "ALPHA"
        self.year.lock_reason = "BETA"
        self.year.save(update_fields=["name", "lock_reason"])
        conflict = self._conflict(
            {"name": "BETA", "lock_reason": "ALPHA", "start_date": "2027-01-15"}
        )

        text = self._run(
            _roster("Ends,Starts\n2027-07-31,2026-09-01\n"),
            match=["Ends=end_date:date"],
            authoritative=["Starts=start_date"],
            derived_split="keep-local",
            apply=True,
        )
        self.assertIn("convention_applied", text)
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, "RESOLVED_MERGE")
        self.assertEqual(str(self._reread().start_date), "2026-09-01")
        self.assertEqual(self._reread().name, "ALPHA")

    def test_an_unknown_convention_is_refused(self):
        with self.assertRaises((CommandError, SystemExit)):
            self._run_silent(derived_split="whatever-you-think")

    def test_the_convention_reaches_only_the_fields_that_prove_the_crossover(self):
        """A row can be unsettled on a name pair AND on something else entirely.

        The crossover is evidence about the NAMES. It says nothing whatever about a
        third field the roster left blank, so deciding that one by a rule about name
        splits is "believe one node" for a field no evidence covers -- the timestamp
        guess wearing a flag, which is what the fence exists to prevent. What is left
        over keeps the row whole, by the same all-or-nothing rule as everything else.
        """
        self.year.name = "ALPHA"
        self.year.lock_reason = "BETA"
        self.year.save(update_fields=["name", "lock_reason"])
        conflict = self._conflict(
            {"name": "BETA", "lock_reason": "ALPHA", "start_date": "2027-01-15"}
        )

        text = self._run(
            _roster("Ends,Starts\n2027-07-31,\n"),
            match=["Ends=end_date:date"],
            authoritative=["Starts=start_date"],
            derived_split="keep-incoming",
            apply=True,
        )

        # The names crossed over; start_date did not, and the roster cell was empty.
        self.assertNotIn("convention_applied", text)
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, "PENDING")
        self.assertEqual(self._reread().name, "ALPHA")
        self.assertEqual(str(self._reread().start_date), "2026-09-01")

    # -- the register contradicting itself -------------------------------------

    CONTESTED = (
        "Term,Official Name\n"
        "2026-09-01,YEAR 2026/2027\n"
        "2027-09-01,YEAR 2026/2027\n"
    )

    def test_a_value_two_lines_claim_settles_neither_of_them(self):
        """The mirror of an ambiguous key, and just as much a non-answer.

        One row reaching two roster lines is already refused. This is the same defect
        from the other side: one roster VALUE claimed by two different lines. A real
        register did it eight times -- two students, one admission number -- and either
        way round it is the register disagreeing with itself, so it is evidence for
        neither and settles nothing.
        """
        conflict = self._conflict({"name": "YEAR 2026/2027"})
        text = self._run(_roster(self.CONTESTED), apply=True)

        self.assertIn("contested_source", text)
        self.assertEqual(self._reread().name, "PROVISIONAL")
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, "PENDING")

    def test_a_contested_value_is_refused_even_with_no_collision_to_notice(self):
        """The quiet half, and the reason a unique constraint is not the guard.

        When only ONE of the pair is in conflict nothing collides -- the write lands, and
        a contested number is recorded as though the register had confirmed it. There is
        no IntegrityError to catch and nothing in the audit trail to look wrong.
        """
        conflict = self._conflict({"name": "YEAR 2026/2027"})
        # No second conflicted row anywhere; the other claimant is simply a line in the
        # file. A constraint would never fire here.
        self._run(_roster(self.CONTESTED), apply=True)

        self.assertEqual(self._reread().name, "PROVISIONAL")
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, "PENDING")

    def test_the_same_line_twice_is_one_claim_not_two(self):
        # Identity is the match key, not the line number: a register that lists a student
        # twice identically has said one thing once, and must still be able to settle it.
        from apps.sync_engine.management.commands import (
            reconcile_sync_conflicts_from_source as cmd,
        )
        from apps.sync_engine.source_authority import KeySpec

        specs = [KeySpec("term", "start_date", "date")]
        rows = [
            {"term": "2026-09-01", "official name": "YEAR 2026/2027"},
            {"term": "2026-09-01", "official name": "YEAR 2026/2027"},
        ]
        contested = cmd.Command()._contested_values(
            rows, specs, {"name": "official name"}
        )
        self.assertEqual(contested["official name"], frozenset())

    def test_a_blank_cell_is_not_contested_however_many_lines_carry_it(self):
        # Otherwise every roster with two empty cells in a column would report its whole
        # column as contradictory, and the finding would be worthless.
        from apps.sync_engine.management.commands import (
            reconcile_sync_conflicts_from_source as cmd,
        )
        from apps.sync_engine.source_authority import KeySpec

        specs = [KeySpec("term", "start_date", "date")]
        rows = [
            {"term": "2026-09-01", "official name": ""},
            {"term": "2027-09-01", "official name": "nan"},
            {"term": "2028-09-01", "official name": "."},
        ]
        contested = cmd.Command()._contested_values(
            rows, specs, {"name": "official name"}
        )
        self.assertEqual(contested["official name"], frozenset())

    def test_a_lone_dot_in_the_roster_settles_nothing(self):
        # The register's mark for "not issued yet". Written as a value it would be a
        # student's official code, and two of them would collide on a unique column.
        conflict = self._conflict({"name": "YEAR 2026/2027"})
        text = self._run(_roster("Term,Official Name\n2026-09-01,.\n"), apply=True)

        self.assertIn("source_silent", text)
        self.assertEqual(self._reread().name, "PROVISIONAL")
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, "PENDING")

    def test_a_row_the_school_does_not_own_is_never_read(self):
        # A roster belongs to one school; matching across schools would let one tenant's
        # file rewrite another's rows.
        from apps.academics.models import AcademicYear

        theirs = AcademicYear.objects.create(
            school=self.other, name="THEIRS",
            start_date="2026-09-01", end_date="2027-07-31",
        )
        self._conflict({"name": "YEAR 2026/2027"}, entity_id=theirs.pk)

        text = self._run(_roster(self.ONE_LINE), apply=True)
        self.assertIn("row_missing", text)
        theirs.refresh_from_db()
        self.assertEqual(theirs.name, "THEIRS")

    def test_another_schools_conflict_is_not_examined(self):
        self._conflict({"name": "YEAR 2026/2027"}, school=self.other)
        text = self._run(_roster(self.ONE_LINE), apply=True)
        self.assertIn("examined: 0", text)

    def test_a_conflict_that_no_longer_differs_is_left_to_the_other_command(self):
        self.year.name = "YEAR 2026/2027"
        self.year.save(update_fields=["name"])
        self._conflict({"name": "YEAR 2026/2027"})
        text = self._run(_roster(self.ONE_LINE), apply=True)
        self.assertIn("not_different", text)

    # -- configuration is refused, not guessed --------------------------------

    def test_a_field_the_rail_does_not_sync_is_refused(self):
        # Correcting it locally would never reach the other node, so accepting it would
        # promise a convergence this cannot deliver.
        with self.assertRaises(CommandError) as ctx:
            self._run(_roster("Term,Official Name\n2026-09-01,X\n"),
                      authoritative=["Official Name=description"])
        self.assertIn("rail", str(ctx.exception))

    def test_a_column_the_source_does_not_have_is_refused_by_name(self):
        with self.assertRaises(CommandError) as ctx:
            self._run(_roster("Term,Official Name\n2026-09-01,X\n"),
                      authoritative=["Missing Column=name"])
        self.assertIn("missing_column", str(ctx.exception))

    def test_an_entity_off_the_rail_is_refused(self):
        with self.assertRaises(CommandError):
            call_command(
                "reconcile_sync_conflicts_from_source",
                school=str(self.school.pk), entity="not_an_entity",
                source=_roster(self.ONE_LINE),
                match=["Term=start_date:date"], authoritative=["Official Name=name"],
                stdout=io.StringIO(),
            )

    def test_a_malformed_clause_is_refused(self):
        for clause in ("no-equals-sign", "=name", "Term="):
            with self.assertRaises(CommandError, msg=clause):
                self._run(_roster(self.ONE_LINE), match=[clause])

    def test_an_empty_source_is_refused(self):
        with self.assertRaises(CommandError):
            self._run(_roster("Term,Official Name\n"))
