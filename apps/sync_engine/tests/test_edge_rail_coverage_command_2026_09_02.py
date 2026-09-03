"""The rail-coverage report must never dress a failed census as good news (2026-09-02).

``edge_rail_coverage`` answers the question an appliance operator actually has: can work
done here reach the cloud? Two things stop it -- a policy that holds the change, and a
model that is not on the rail at all. The second is invisible in production: no error, no
conflict, no refusal, the rows simply stay where they were written. ``--counts`` puts a
number on it.

WHICH MEANS THE NUMBER HAS TO BE HONEST. The first cut of this command printed

    ROWS THAT CANNOT TRAVEL ...... 0
    models this deployment could not read: 353 (not migrated here?)

on a deployment where it had read NOTHING. A zero derived from 353 failed reads is not a
zero; it is a failure wearing the shape of good news, and it is the same confusion that
let a delete bundle report ``deleted 0`` while 46 rows went unaccounted for. So the census
now refuses to print a bare total whenever any model was unreadable, and says AT LEAST.

The structural half of the report needs no fixture: it is derived from the registries and
is true of any deployment. The census half is driven through a patched ``_count`` so both
branches -- complete and incomplete -- are exercised deterministically, rather than
depending on which tables happen to exist in the test database.
"""
from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase

_COUNT = "apps.sync_engine.management.commands.edge_rail_coverage._count"


def _run(*args):
    out = StringIO()
    call_command("edge_rail_coverage", *args, stdout=out, stderr=StringIO())
    return out.getvalue()


class AFailedCensusIsNeverReportedAsZeroTests(SimpleTestCase):
    """LOAD-BEARING. Each fails on the first cut of this command."""

    def test_an_unreadable_model_makes_the_total_a_floor(self):
        with patch(_COUNT, return_value=None):
            text = _run("--counts")
        self.assertIn("CENSUS INCOMPLETE", text)
        self.assertIn("AT LEAST", text)

    def test_it_says_how_many_models_it_actually_read(self):
        # "0 of 353" is the line that makes the failure legible at a glance. Without it a
        # reader has to notice a separate caveat line and do the subtraction themselves.
        with patch(_COUNT, return_value=None):
            text = _run("--counts")
        self.assertIn("models read", text)
        self.assertIn("0 of", text)

    def test_a_partial_census_is_still_a_floor(self):
        # The dangerous middle case: MOST models read fine, a few did not. The total looks
        # authoritative and is not. One unreadable model is enough to demote it.
        seq = iter([5] + [None] * 5000)

        def _some_fail(model, school=None):
            return next(seq, 0)

        with patch(_COUNT, side_effect=_some_fail):
            text = _run("--counts")
        self.assertIn("CENSUS INCOMPLETE", text)
        self.assertNotIn("ROWS THAT CANNOT TRAVEL", text)

    def test_the_json_carries_the_incompleteness_flag(self):
        # A consumer must be able to tell a total from a floor without re-deriving it.
        import json

        with patch(_COUNT, return_value=None):
            payload = json.loads(_run("--counts", "--json"))
        self.assertFalse(payload["census_complete"])


class ACompleteCensusReportsPlainlyTests(SimpleTestCase):
    """CONTROL. The warning has to be a signal, not permanent furniture."""

    def test_a_readable_deployment_gets_a_confident_total(self):
        with patch(_COUNT, return_value=0):
            text = _run("--counts")
        self.assertIn("ROWS THAT CANNOT TRAVEL", text)
        self.assertNotIn("CENSUS INCOMPLETE", text)

    def test_rows_are_totalled_and_the_largest_are_named(self):
        with patch(_COUNT, return_value=7):
            text = _run("--counts", "--top", "3")
        self.assertIn("largest, this deployment:", text)

    def test_the_json_flag_is_true_when_everything_was_read(self):
        import json

        with patch(_COUNT, return_value=0):
            payload = json.loads(_run("--counts", "--json"))
        self.assertTrue(payload["census_complete"])


class TheStructuralReportIsTrueOfAnyDeploymentTests(SimpleTestCase):
    """No fixture: these come from the registries, so they hold on a box and on the cloud."""

    def test_it_names_what_a_box_may_not_create(self):
        # `teacher` is refused on create because minting an accounts.User is an
        # authentication decision, not a data merge. An operator has to be told that
        # plainly, or a staff import that "did nothing" looks like a bug.
        self.assertIn("teacher", _run())

    def test_it_names_what_a_box_edit_cannot_silently_change(self):
        text = _run()
        self.assertIn("evaluation", text)
        self.assertIn("invoice", text)

    def test_it_reports_the_coverage_gap_at_all(self):
        # The headline the whole command exists for: most tenant data is not on the rail.
        text = _run()
        self.assertIn("WHAT THE RAIL DOES NOT CARRY", text)
        self.assertIn("NOT registered on the rail", text)

    def test_without_counts_it_says_how_to_get_them(self):
        text = _run()
        self.assertIn("--counts", text)
        self.assertNotIn("ROWS THAT CANNOT TRAVEL", text)

    def test_the_json_shape_is_stable(self):
        import json

        payload = json.loads(_run("--json"))
        for key in ("registered_entities", "tenant_scoped_models", "models_not_on_rail",
                    "entities", "protected", "insert_held", "unclassified"):
            self.assertIn(key, payload)
        # student_guardian joined teacher on 2026-09-03: the link names a login
        # and grants access to a child's records, so creation stays an identity
        # decision while contact edits converge.
        self.assertEqual(payload["insert_held"], ["student_guardian", "teacher"])
        self.assertEqual(payload["unclassified"], [])
