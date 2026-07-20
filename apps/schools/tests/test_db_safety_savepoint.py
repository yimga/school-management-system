"""A swallowed database error must not take the rest of the transaction with it.

The bug (G3): PostgreSQL aborts the whole transaction on any statement error, so
``except Exception: pass`` around a failing query leaves the connection in
``InFailedSqlTransaction`` and every LATER statement fails for an unrelated
reason. It killed a real provisioning drive.

These are must-FIRE tests. The load-bearing one asserts that work done inside the
suppressed block is ROLLED BACK while work done before and after it survives —
which is exactly what a savepoint buys and what a bare try/except does not.
A test that only checked "no exception escaped" would pass against the broken
code too.
"""
from __future__ import annotations

from django.db import DatabaseError, IntegrityError, transaction
from django.test import TestCase

from apps.schools.db_safety import savepoint_call, savepoint_suppress
from apps.schools.models import School


def _school(slug: str) -> School:
    return School.objects.create(
        name=slug, slug=slug, subdomain=slug, country_code="CM", is_active=True
    )


class SavepointSuppressTests(TestCase):
    def test_block_writes_roll_back_but_the_transaction_survives(self):
        """The whole point: partial work is undone, surrounding work is not."""
        with transaction.atomic():
            _school("sp-before")
            with savepoint_suppress(DatabaseError, context="unit") as outcome:
                _school("sp-inside")
                raise IntegrityError("simulated statement failure")
            self.assertFalse(outcome.ok)
            # The transaction is still usable — this is what was broken.
            _school("sp-after")

        slugs = set(School.objects.values_list("slug", flat=True))
        self.assertIn("sp-before", slugs)
        self.assertIn("sp-after", slugs)
        self.assertNotIn(
            "sp-inside", slugs, "the failed block's writes were not rolled back"
        )

    def test_outcome_reports_the_failure_rather_than_hiding_it(self):
        with savepoint_suppress(DatabaseError, context="reporting") as outcome:
            raise IntegrityError("boom")
        self.assertFalse(outcome.ok)
        self.assertFalse(bool(outcome))
        self.assertIsInstance(outcome.error, IntegrityError)
        self.assertEqual(outcome.context, "reporting")

    def test_success_path_commits_and_reports_ok(self):
        with savepoint_suppress(DatabaseError, context="ok") as outcome:
            _school("sp-ok")
        self.assertTrue(outcome.ok)
        self.assertIsNone(outcome.error)
        self.assertTrue(School.objects.filter(slug="sp-ok").exists())

    def test_unlisted_exception_is_not_swallowed(self):
        """Suppression is a decision, not a blanket. A ValueError still escapes."""
        with self.assertRaises(ValueError):
            with savepoint_suppress(DatabaseError, context="narrow"):
                raise ValueError("not a database problem")

    def test_reraise_still_rolls_back_to_the_savepoint(self):
        with self.assertRaises(IntegrityError):
            with savepoint_suppress(DatabaseError, context="reraise", reraise=True):
                raise IntegrityError("boom")

    def test_savepoint_call_returns_default_on_failure(self):
        def _boom():
            raise IntegrityError("boom")

        self.assertEqual(savepoint_call(_boom, context="call", default=0), 0)
        self.assertEqual(savepoint_call(lambda: 7, context="call", default=0), 7)
