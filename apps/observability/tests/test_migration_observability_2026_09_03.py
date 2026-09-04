"""A deploy that skipped its migrations must not look like one that ran them.

``SKIP_DB_MIGRATIONS=1`` short-circuits the entire migrate block in
``scripts/release/render_predeploy.sh``. It is set in the Render dashboard, so it
appears in no committed file, and the old code simply fell through the ``if``
with nothing logged. The consequence was concrete: on 2026-09-02 the question
"did accounts migration 0060 actually apply in production?" could only be
answered by INFERENCE from the deploy config -- there was no observable fact
anywhere that said so.

Two facts are reported, and the distinction is the point. ``skip_db_migrations``
is what was *asked for*; ``unapplied_count`` is what is *true of the database*.
A skip against an already-current database is harmless, and a deploy that ran
migrations can still leave drift. Only the second field can tell those apart, so
a test that checked only the flag would be re-certifying the blind spot.
"""

from __future__ import annotations

import os
from unittest import mock

from django.test import TestCase

from apps.observability.views import _migration_state


class WhatTheFlagSaysTests(TestCase):
    def test_reports_the_effective_flag_when_set(self):
        with mock.patch.dict(os.environ, {"SKIP_DB_MIGRATIONS": "1"}):
            self.assertEqual(_migration_state()["skip_db_migrations"], "1")

    def test_defaults_to_0_when_unset(self):
        # patch.dict(clear=True) would wipe every other variable for the
        # duration, and Django settings read the environment lazily -- remove
        # only the one key.
        with mock.patch.dict(os.environ):
            os.environ.pop("SKIP_DB_MIGRATIONS", None)
            self.assertEqual(_migration_state()["skip_db_migrations"], "0")


class WhatTheDatabaseSaysTests(TestCase):
    def test_reports_the_truth_independently_of_the_flag(self):
        """The flag must never be the source of applied_ok.

        Claiming the DB is current *because* nobody asked to skip is exactly the
        reasoning this endpoint exists to replace.
        """
        with mock.patch.dict(os.environ, {"SKIP_DB_MIGRATIONS": "1"}):
            skipped = _migration_state()
        with mock.patch.dict(os.environ, {"SKIP_DB_MIGRATIONS": "0"}):
            ran = _migration_state()
        self.assertEqual(skipped["applied_ok"], ran["applied_ok"])
        self.assertEqual(skipped["unapplied_count"], ran["unapplied_count"])

    def test_the_test_database_is_current(self):
        state = _migration_state()
        self.assertTrue(state["applied_ok"], state.get("unapplied"))
        self.assertEqual(state["unapplied_count"], 0)

    def test_unapplied_list_is_capped(self):
        self.assertLessEqual(len(_migration_state().get("unapplied", [])), 20)

    def test_a_database_error_is_reported_not_raised(self):
        """A health endpoint must never 500 because it could not introspect."""
        with mock.patch(
            "django.db.migrations.executor.MigrationExecutor",
            side_effect=ValueError("graph exploded"),
        ):
            state = _migration_state()
        self.assertIn("error", state)
        self.assertNotIn("applied_ok", state)
        self.assertEqual(state["skip_db_migrations"], os.environ.get("SKIP_DB_MIGRATIONS", "0"))


class TheDeployScriptAnnouncesBothBranchesTests(TestCase):
    """The log line is the other half: healthz answers 'now', the log answers 'then'."""

    def _script(self):
        from pathlib import Path

        return Path("scripts/release/render_predeploy.sh").read_text(
            encoding="utf-8", errors="replace"
        )

    def test_the_running_branch_says_so(self):
        self.assertIn("-> RUNNING database migrations", self._script())

    def test_the_skipping_branch_says_so(self):
        script = self._script()
        self.assertIn("-> SKIPPING database migrations", script)
        self.assertIn("were NOT applied for this deploy", script)

    def test_a_skip_still_reports_actual_drift(self):
        """A deliberate skip must still say what is true of the database."""
        script = self._script()
        tail = script.split("-> SKIPPING database migrations", 1)[1]
        self.assertIn("verify_all_migrations_applied", tail)
