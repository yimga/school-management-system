"""The sweep that closes conflicts which are not disagreements -- and only those.

A conflict record says "two sides disagree, a human must choose". Tens of thousands of
them said no such thing: the apply path graded them on timestamps before checking whether
the incoming row would change anything, so a box that had already converged filed a
conflict against every row a full-corpus re-pull re-offered. That ordering is fixed, but
the records it wrote do not disappear, and 68,000 of them is not a thing anyone can work
through by hand.

This command re-reads each PENDING conflict, compares the client payload against the row
as it stands NOW, and resolves only the ones where every comparable value already matches.
It is also the PROOF rather than an assertion: if it clears nearly all of them the
conflicts were manufactured; if it leaves thousands the disagreements were real and we
find that out instead of having assumed it.

What the tests below pin, in order of how much damage getting them wrong would do:

  1. A real disagreement is NEVER resolved. This is the whole safety property.
  2. Reads are scoped to the conflict's own school. A sweep that can read another
     tenant's row to decide a resolution is a security defect, not a bug.
  3. Nothing is written without --apply.
  4. The cases it cannot decide (row gone, entity not on the rail, nothing comparable in
     the payload) stay PENDING and are reported, rather than being quietly counted as
     handled.
"""
from __future__ import annotations

import json
import uuid
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.academics.models import Department
from apps.schools.models import School
from apps.siteconfig.models import SyncConflict

COMMAND = "resolve_identical_sync_conflicts"


class _Fixture(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Sweep {uid}", slug=f"sweep-{uid}", subdomain=f"sweep{uid}", is_active=True
        )
        self.dept = Department.objects.create(
            school=self.school, name="Sciences", code=f"SCI-{uid}"
        )

    def _conflict(self, *, entity="department", pk=None, client=None, school=None):
        return SyncConflict.objects.create(
            school=school or self.school,
            entity_type=entity,
            entity_id=self.dept.pk if pk is None else pk,
            client_data=client if client is not None else {"name": "Sciences"},
            server_data={"name": "Sciences"},
            status=SyncConflict.Status.PENDING,
        )

    def _run(self, *args, **opts):
        out = StringIO()
        call_command(COMMAND, *args, stdout=out, **opts)
        return out.getvalue()

    def _json(self, *args, **opts):
        return json.loads(self._run(*args, json=True, **opts))


class ItMustNotResolveARealDisagreementTests(_Fixture):
    """The safety property. Everything else is convenience; this one is correctness."""

    def test_a_differing_payload_is_left_pending(self):
        conflict = self._conflict(client={"name": "Renamed"})
        report = self._json(apply=True)

        conflict.refresh_from_db()
        self.assertEqual(conflict.status, SyncConflict.Status.PENDING)
        self.assertEqual(report["resolved"], 0)
        self.assertEqual(report["outcomes"]["differs"], 1)

    def test_one_differing_field_among_matching_ones_is_enough(self):
        conflict = self._conflict(client={"name": "Sciences", "code": "CHANGED"})
        self._run(apply=True)
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, SyncConflict.Status.PENDING)

    def test_a_matching_payload_is_resolved_as_keeping_the_server_copy(self):
        conflict = self._conflict()
        report = self._json(apply=True)

        conflict.refresh_from_db()
        self.assertEqual(conflict.status, SyncConflict.Status.RESOLVED_SERVER)
        self.assertIsNotNone(conflict.resolved_at)
        self.assertIn("identical", conflict.resolution_note)
        self.assertEqual(report["resolved"], 1)

    def test_the_row_itself_is_never_touched(self):
        # "Resolved" here means the disagreement was imaginary, not that a value was
        # chosen. Writing anything would make the sweep a data change.
        before = Department.objects.get(pk=self.dept.pk).updated_at
        self._conflict()
        self._run(apply=True)
        after = Department.objects.get(pk=self.dept.pk)
        self.assertEqual(after.updated_at, before)
        self.assertEqual(after.name, "Sciences")

    def test_a_mixed_backlog_splits_correctly(self):
        real = self._conflict(client={"name": "Renamed"})
        fake = [self._conflict() for _ in range(5)]
        report = self._json(apply=True)

        self.assertEqual(report["resolved"], 5)
        self.assertEqual(report["outcomes"]["identical"], 5)
        self.assertEqual(report["outcomes"]["differs"], 1)
        real.refresh_from_db()
        self.assertEqual(real.status, SyncConflict.Status.PENDING)
        for conflict in fake:
            conflict.refresh_from_db()
            self.assertEqual(conflict.status, SyncConflict.Status.RESOLVED_SERVER)


class ItMustNotReadAnotherTenantsRowTests(_Fixture):
    """A sweep that resolves school A's conflict by reading school B's row is a breach."""

    def test_a_pk_belonging_to_another_school_is_not_treated_as_a_match(self):
        uid = uuid.uuid4().hex[:8]
        other = School.objects.create(
            name=f"Other {uid}", slug=f"other-{uid}", subdomain=f"other{uid}", is_active=True
        )
        theirs = Department.objects.create(
            school=other, name="Sciences", code=f"OSCI-{uid}"
        )
        # Same values, same entity type, a pk this school does not own.
        conflict = self._conflict(pk=theirs.pk)
        report = self._json(apply=True)

        conflict.refresh_from_db()
        self.assertEqual(conflict.status, SyncConflict.Status.PENDING)
        self.assertEqual(report["outcomes"]["row_missing"], 1)
        self.assertEqual(report["resolved"], 0)

    def test_scoping_to_one_school_does_not_examine_the_others(self):
        uid = uuid.uuid4().hex[:8]
        other = School.objects.create(
            name=f"Third {uid}", slug=f"third-{uid}", subdomain=f"third{uid}", is_active=True
        )
        self._conflict()
        self._conflict(school=other)
        report = self._json(apply=True, school=str(self.school.pk))
        self.assertEqual(report["examined"], 1)


class ItMustWriteNothingWithoutApplyTests(_Fixture):
    def test_a_dry_run_leaves_every_conflict_pending(self):
        conflict = self._conflict()
        report = self._json()

        conflict.refresh_from_db()
        self.assertEqual(conflict.status, SyncConflict.Status.PENDING)
        self.assertFalse(report["applied"])

    def test_a_dry_run_reports_what_it_would_close(self):
        # The number an operator decides on has to be the number they will get.
        for _ in range(3):
            self._conflict()
        self.assertEqual(self._json()["resolved"], 3)
        self.assertEqual(self._json(apply=True)["resolved"], 3)

    def test_the_human_report_says_so_out_loud(self):
        self._conflict()
        self.assertIn("DRY RUN", self._run())
        self.assertNotIn("DRY RUN", self._run(apply=True))


class ItMustReportWhatItCannotDecideTests(_Fixture):
    """Each of these stays PENDING and is NAMED. Silence would read as 'handled'."""

    def test_a_deleted_row_is_left_for_a_human(self):
        conflict = self._conflict(pk=99999999)
        report = self._json(apply=True)
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, SyncConflict.Status.PENDING)
        self.assertEqual(report["outcomes"]["row_missing"], 1)

    def test_an_entity_the_rail_does_not_know_is_left_alone(self):
        conflict = self._conflict(entity="not_a_rail_entity")
        report = self._json(apply=True)
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, SyncConflict.Status.PENDING)
        self.assertEqual(report["outcomes"]["unknown_entity"], 1)

    def test_a_payload_with_no_syncable_field_is_left_alone(self):
        # Nothing comparable is not the same as nothing different.
        conflict = self._conflict(client={"not_a_field": 1})
        report = self._json(apply=True)
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, SyncConflict.Status.PENDING)
        self.assertEqual(report["outcomes"]["no_comparable_fields"], 1)

    def test_an_empty_payload_is_left_alone(self):
        conflict = self._conflict(client={})
        self._run(apply=True)
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, SyncConflict.Status.PENDING)

    def test_the_report_breaks_the_backlog_down_by_entity(self):
        # How an operator confirms the diagnosis: if one entity is almost entirely
        # `identical`, its conflicts were manufactured.
        self._conflict()
        self._conflict(client={"name": "Renamed"})
        report = self._json(apply=True)
        self.assertEqual(
            report["by_entity"]["department"], {"identical": 1, "differs": 1}
        )


class ItMustNotTouchAResolvedConflictTests(_Fixture):
    def test_an_already_resolved_conflict_is_never_examined(self):
        conflict = self._conflict()
        conflict.status = SyncConflict.Status.RESOLVED_CLIENT
        conflict.save(update_fields=["status"])

        report = self._json(apply=True)
        self.assertEqual(report["examined"], 0)
        conflict.refresh_from_db()
        self.assertEqual(conflict.status, SyncConflict.Status.RESOLVED_CLIENT)

    def test_an_empty_backlog_reports_cleanly(self):
        report = self._json(apply=True)
        self.assertEqual(report["examined"], 0)
        self.assertEqual(report["resolved"], 0)


class ItMustHonourItsOwnBoundsTests(_Fixture):
    def test_limit_stops_after_the_requested_number(self):
        for _ in range(5):
            self._conflict()
        report = self._json(apply=True, limit=2)
        self.assertEqual(report["examined"], 2)
        self.assertEqual(report["resolved"], 2)
        self.assertEqual(
            SyncConflict.objects.filter(status=SyncConflict.Status.PENDING).count(), 3
        )

    def test_a_chunk_smaller_than_the_backlog_still_resolves_all_of_it(self):
        # The batching is what makes 68,000 rows survivable; an off-by-one there would
        # silently leave a tail behind.
        for _ in range(7):
            self._conflict()
        report = self._json(apply=True, chunk=2)
        self.assertEqual(report["resolved"], 7)
        self.assertEqual(
            SyncConflict.objects.filter(status=SyncConflict.Status.PENDING).count(), 0
        )

    def test_entity_narrows_the_sweep(self):
        self._conflict()
        self._conflict(entity="subject")
        report = self._json(apply=True, entity="department")
        self.assertEqual(report["examined"], 1)


class ItMustSayWhatActuallyDisagreesTests(_Fixture):
    """Counts tell you HOW MANY are real. They do not tell you what happened.

    389 student conflicts is either one bulk operation on the cloud that never landed, or
    389 separate human decisions -- and the remedy is completely different. The only thing
    that separates them is WHICH fields disagree, so the sweep tallies every differing
    field rather than the first one, which would only report whichever column sorts
    earliest.
    """

    def test_it_tallies_every_differing_field_not_just_the_first(self):
        self._conflict(client={"name": "Renamed", "code": "CHANGED"})
        report = self._json(explain=True)
        self.assertEqual(
            report["differing_fields"]["department"], {"name": 1, "code": 1}
        )

    def test_a_field_that_disagrees_on_every_row_stands_out_by_count(self):
        # The bulk-operation signature: one column, every conflicted row.
        for _ in range(4):
            self._conflict(client={"name": "Sciences", "code": "MOVED"})
        report = self._json(explain=True)
        self.assertEqual(report["differing_fields"]["department"], {"code": 4})

    def test_identical_conflicts_contribute_nothing_to_the_tally(self):
        self._conflict()
        self._conflict(client={"name": "Renamed"})
        report = self._json(explain=True)
        self.assertEqual(report["differing_fields"]["department"], {"name": 1})

    def test_the_tally_is_absent_unless_asked_for(self):
        self._conflict(client={"name": "Renamed"})
        self.assertEqual(self._json()["differing_fields"], {})

    def test_the_human_report_names_the_fields(self):
        self._conflict(client={"name": "Renamed"})
        out = self._run(explain=True)
        self.assertIn("what actually disagrees", out)
        self.assertIn("name", out)


class ItMustNotPrintTenantValuesUnlessAskedTests(_Fixture):
    """Samples carry names and codes to a terminal. That has to be a deliberate flag."""

    def test_no_samples_by_default(self):
        self._conflict(client={"name": "Renamed"})
        self.assertEqual(self._json(explain=True)["samples"], [])

    def test_a_sample_carries_both_sides_and_both_stamps(self):
        self._conflict(client={"name": "Renamed"})
        sample = self._json(sample=5)["samples"][0]
        self.assertEqual(sample["entity"], "department")
        self.assertEqual(sample["id"], self.dept.pk)
        self.assertEqual(
            sample["fields"]["name"], {"incoming": "Renamed", "local": "Sciences"}
        )
        self.assertIn("incoming_stamp", sample)
        self.assertIn("local_stamp", sample)

    def test_the_sample_cap_is_honoured(self):
        for _ in range(6):
            self._conflict(client={"name": "Renamed"})
        self.assertEqual(len(self._json(sample=2)["samples"]), 2)

    def test_identical_conflicts_are_never_sampled(self):
        for _ in range(3):
            self._conflict()
        self.assertEqual(self._json(sample=5)["samples"], [])
