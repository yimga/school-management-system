"""A failing decision-log write must not poison the caller's transaction.

``decide`` is ``@transaction.atomic`` and its ``PolicyDecisionLog.objects.create``
sat inside a bare ``try/except Exception: pass`` with NO savepoint. That is the
exact shape Django's docs warn against: a query raises inside an atomic block and
the exception is swallowed, so Django never learns the transaction is broken. On
PostgreSQL the connection is left in "current transaction is aborted, commands
ignored until end of transaction block" and the caller's NEXT query -- against a
completely unrelated table -- is the one that 500s, which makes the real cause
(a policy log row) undiscoverable from the traceback.

**SQLite cannot show that symptom**: a failed INSERT leaves the transaction
perfectly usable, so a behavioural test here would be green against fully broken
code. What IS observable on every backend, and is exactly the missing mechanism,
is the savepoint: with the fix the log write runs one atomic level deeper than
``decide`` itself, so a failure rolls back to that savepoint and hands the caller
a usable connection. These tests measure that depth at the moment the write is
attempted.

The same shape in ``_inject_rebac_context`` is covered by the second class.
"""

from __future__ import annotations

import logging
import uuid
from unittest import mock

from django.db import DatabaseError, connection, transaction
from django.test import TestCase

from apps.policies import pdp
from apps.policies.models import PolicyDecisionLog
from apps.schools.models import School


def _make_school() -> School:
    tag = uuid.uuid4().hex[:8]
    return School.objects.create(
        name=f"PDP High {tag}",
        slug=f"pdp-{tag}",
        subdomain=f"pdp-{tag}",
        is_active=True,
    )


class DecisionLogWriteIsSavepointedTests(TestCase):
    """The log INSERT must sit one atomic level below ``decide``'s own block."""

    def setUp(self) -> None:
        self.school = _make_school()
        self.subject = {"user_id": None, "role": "TEACHER"}
        self.resource = {"entity": "student", "id": 1}

    def _depth_at_log_write(self, *, raise_error):
        """Run decide() and capture the savepoint depth inside the log write."""
        captured: dict = {}
        real_create = PolicyDecisionLog.objects.create

        def spy(*args, **kwargs):
            captured["depth"] = len(connection.savepoint_ids)
            captured["called"] = True
            if raise_error:
                raise DatabaseError("simulated log-write failure")
            return real_create(*args, **kwargs)

        outer_depth = len(connection.savepoint_ids)
        with mock.patch.object(PolicyDecisionLog.objects, "create", side_effect=spy):
            decision = pdp.decide(
                self.subject, "read", self.resource, school=self.school
            )
        # Non-vacuity: the write really was attempted. Without this a decide() that
        # skipped logging entirely (log=False, an early return, a renamed model)
        # would sail through every assertion below.
        self.assertTrue(captured.get("called"), "the decision log write never ran")
        return outer_depth, captured["depth"], decision

    def test_log_write_runs_inside_its_own_savepoint(self) -> None:
        outer, inner, _ = self._depth_at_log_write(raise_error=False)
        # decide() is @transaction.atomic, so entering it opens one savepoint
        # (TestCase already holds an atomic block). The log write must open a
        # SECOND one -- that is the savepoint a failure rolls back to.
        self.assertGreaterEqual(
            inner,
            outer + 2,
            "PolicyDecisionLog.objects.create is not wrapped in its own "
            "transaction.atomic() -- a DB error there leaves the connection "
            "aborted for the rest of the request on PostgreSQL",
        )

    def test_a_failing_log_write_still_returns_the_decision(self) -> None:
        _, _, decision = self._depth_at_log_write(raise_error=True)
        # The original contract is preserved: logging failure must not block the
        # decision itself.
        self.assertIsNotNone(decision)
        self.assertEqual(decision.effect, "implicit_deny")

    def test_a_failing_log_write_leaves_the_connection_usable(self) -> None:
        self._depth_at_log_write(raise_error=True)
        # A query the caller would run next. On SQLite this passes either way --
        # it is the savepoint assertion above that carries the Postgres proof.
        self.assertTrue(School.objects.filter(pk=self.school.pk).exists())

    def test_a_failing_log_write_is_logged_not_swallowed_silently(self) -> None:
        # config/settings_test.py calls logging.disable(logging.CRITICAL) at import,
        # so assertLogs sees nothing until it is lifted for the duration of the test.
        logging.disable(logging.NOTSET)
        self.addCleanup(logging.disable, logging.CRITICAL)
        with self.assertLogs("apps.policies.pdp", level="WARNING") as captured_logs:
            self._depth_at_log_write(raise_error=True)
        self.assertTrue(
            any("decision log" in line.lower() for line in captured_logs.output),
            f"expected a warning naming the decision log; got {captured_logs.output}",
        )


class RebacContextInjectionIsSavepointedTests(TestCase):
    """``_inject_rebac_context`` does the same unguarded DB read."""

    def setUp(self) -> None:
        self.school = _make_school()

    def test_user_lookup_runs_inside_its_own_savepoint(self) -> None:
        captured: dict = {}

        def spy(*args, **kwargs):
            captured["depth"] = len(connection.savepoint_ids)
            captured["called"] = True
            raise DatabaseError("simulated rebac lookup failure")

        ctx: dict = {"resource": {"permission_code": "grade.submit"}}
        with mock.patch("apps.accounts.rebac.rebac_enabled", return_value=True):
            with mock.patch(
                "apps.accounts.models.User.objects.filter", side_effect=spy
            ):
                with transaction.atomic():
                    outer_depth = len(connection.savepoint_ids)
                    pdp._inject_rebac_context(
                        ctx, {"user_id": 1, "role": "TEACHER"}, self.school
                    )
        # Non-vacuity: rebac was enabled and the lookup really was reached, so the
        # depth below is measured at the DB access and not at some early return.
        self.assertTrue(captured.get("called"), "the rebac user lookup never ran")
        self.assertGreaterEqual(
            captured["depth"],
            outer_depth + 1,
            "the rebac User lookup is not wrapped in its own transaction.atomic()",
        )
        # The documented fallback still holds.
        self.assertEqual(ctx["rebac"], {"permission_code": "grade.submit", "allowed": False})
