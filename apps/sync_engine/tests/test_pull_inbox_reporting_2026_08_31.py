"""The pull command must ACCOUNT for every row the cloud sent it (2026-08-31).

``apply_pulled_bundle`` returns eight buckets. ``pull_edge_inbox`` printed six, dropping
``deleted`` and ``skipped``, so its output did not add up and could not be made to add up
by an operator reading it. Measured on the Gilead box the same day, both failure modes of
that silence appeared within hours of each other:

  * ``Pulled 75755 -> applied 75709``. The 46 were DELETIONS, applied exactly as intended.
    Nothing was wrong, and the output gave no way to know that.
  * ``Pulled 26 -> applied 0``. Every row was REFUSED. The output shape was identical --
    a received count larger than an applied count -- and the reason dict naming the
    refusal had already been computed by ``tally_skipped_rows`` and thrown away.

So these tests assert on the COMMAND'S OUTPUT, not on the apply result: the result was
never the thing that was broken. ``apply_pulled_bundle`` is stubbed to return a fixed
tally precisely so that a change to the apply path can never make them pass or fail for
the wrong reason -- what is under test is whether the numbers reach a human.
"""
from __future__ import annotations

import uuid
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import User
from apps.schools.models import School, SchoolMembership

_PULL = "apps.sync_engine.edge_outbox.pull_bundle"
_APPLY = "apps.sync_engine.edge_inbox.apply_pulled_bundle"


def _result(**overrides):
    """A full apply tally. Defaults are a clean pull; each test perturbs one bucket."""
    base = {
        "ok": True,
        "received": 0,
        "applied": 0,
        "created": 0,
        "upserted": 0,
        "deleted": 0,
        "already_absent": 0,
        "soft_deleted": 0,
        "conflicts": 0,
        "malformed": 0,
        "skipped": 0,
        "unaccounted": 0,
        "skipped_reasons": {},
        "skipped_missing_parents": {},
        "conflict_details": [],
        "results": [],
        "insert_results": [],
        "delete_results": [],
    }
    base.update(overrides)
    return base


class _PullCommandCaller:
    """Run the command with the network and the apply path both stubbed.

    ``--token`` and ``--endpoint`` are passed explicitly so a run does not depend on this
    machine being paired to an operator; the bundle body is never parsed, because apply
    is stubbed.
    """

    def _run(self, result):
        out = StringIO()
        with patch(_PULL, return_value=(200, b"{}", "")), patch(_APPLY, return_value=result):
            call_command(
                "pull_edge_inbox",
                "--slug", self.school.slug,
                "--token", "test-credential",
                "--endpoint", "https://operator.invalid/api/sync/bundle/",
                "--since", "1970-01-01T00:00:00+00:00",
                stdout=out,
            )
        return out.getvalue()

    def _provision(self, label):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"{label} {uid}",
            slug=f"{label}-{uid}",
            subdomain=f"{label}{uid}",
            is_active=True,
        )
        self.user = User.objects.create_superuser(
            username=f"{label}_admin_{uid}",
            password="Test1234",
            email=f"{label}{uid}@test.com",
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )


class PullInboxAccountsForEveryRowTests(_PullCommandCaller, TestCase):
    def setUp(self):
        self._provision("edge")

    def test_a_refused_row_is_reported_as_skipped(self):
        # The 26-teacher case: everything received, nothing applied. Before this fix the
        # word "skipped" did not appear in the output at any count.
        text = self._run(_result(received=26, applied=0, skipped=26,
                                 skipped_reasons={"insert_held_for_entity": 26}))
        self.assertIn("skipped 26", text)

    def test_the_reason_for_a_refusal_is_named(self):
        # A count alone still forces an operator into a shell to ask WHY. The reason is
        # already in hand; the only question was ever whether it was printed.
        text = self._run(_result(received=26, applied=0, skipped=26,
                                 skipped_reasons={"insert_held_for_entity": 26}))
        self.assertIn("insert_held_for_entity x26", text)

    def test_deletions_are_counted_so_the_tally_closes(self):
        # The 46-tombstone case, with the fixture CORRECTED on 2026-09-02.
        #
        # This test used to stub `deleted=46` and assert the line said so. The box
        # never returned that. `apply_deletes` answered 200 for all 46 while removing
        # nothing -- `deleted 0` -- because the rows were already gone, and this file
        # had invented the one number that would have made the tally close. So the
        # claim in the commit message, that the printed buckets sum to `received`,
        # was proved by a fixture rather than by the rail, and shipped false.
        #
        # It is not a small distinction. Those 46 were the residue of a deletion that
        # had ALREADY destroyed 13 teacher records, and `deleted 0, skipped 0` is what
        # that looked like going past. The real shape is asserted here now.
        text = self._run(_result(
            received=75755, applied=75709, deleted=0, already_absent=46
        ))
        self.assertIn("deleted 0", text)
        self.assertIn("already absent 46", text)

    def test_the_absent_parent_is_named_not_just_counted(self):
        # missing_reference is the one reason whose REPAIR depends on which parent it is:
        # a parent that rides the rail is cured by a full re-pull, one that does not ride
        # never will be. tally_skipped_rows keeps the label for this; print it.
        text = self._run(_result(
            received=10, applied=7, skipped=3,
            skipped_reasons={"missing_reference": 3},
            skipped_missing_parents={"people.TeacherProfile": 3},
        ))
        self.assertIn("people.TeacherProfile x3", text)

    def test_a_tally_that_does_not_close_says_so(self):
        # The seal the previous pass lacked. A remainder means some outcome is going
        # unreported, which is the state this rail was in while it deleted teachers;
        # an operator must not have to subtract the line themselves to find out.
        text = self._run(_result(received=75755, applied=75709, unaccounted=46))
        self.assertIn("TALLY DOES NOT CLOSE", text)
        self.assertIn("46 of 75755", text)

    def test_a_closing_tally_stays_quiet_about_it(self):
        # CONTROL for the line above: the warning must be a signal, not furniture.
        text = self._run(_result(received=500, applied=500))
        self.assertNotIn("TALLY DOES NOT CLOSE", text)

    def test_a_clean_pull_still_names_its_zero(self):
        # The tally must close on a HEALTHY pull too. A bucket that appears only
        # when non-zero teaches an operator nothing about what the absence meant
        # the rest of the time -- "skipped" has to be a number they have seen at 0.
        text = self._run(_result(received=500, applied=500))
        self.assertIn("skipped 0", text)

    def test_several_reasons_are_all_reported(self):
        # A mixed bundle must not report only the first reason, or only the largest.
        text = self._run(_result(
            received=100, applied=90, skipped=10,
            skipped_reasons={"create_failed": 6, "insert_held_for_entity": 4},
        ))
        self.assertIn("create_failed x6", text)
        self.assertIn("insert_held_for_entity x4", text)


class ACleanPullStaysQuietTests(_PullCommandCaller, TestCase):
    """CONTROL. The point is to surface refusals, not to add noise to a healthy box that
    syncs on a schedule. Without these, "print the reasons" could become "print an empty
    dict every cycle", and an operator learns to skip past the line that matters."""

    def setUp(self):
        self._provision("quiet")

    def test_no_refusal_line_when_nothing_was_refused(self):
        text = self._run(_result(received=500, applied=500))
        self.assertNotIn("NOT applied", text)
        self.assertNotIn("absent parent", text)

    def test_the_headline_survives(self):
        # Guards the other direction: adding buckets must not cost the summary
        # line every operator already reads. True before the fix and after it --
        # which is what makes it a control rather than a second assertion of it.
        text = self._run(_result(received=500, applied=500))
        self.assertIn("Pulled 500 row(s)", text)
