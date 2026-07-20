"""Swallowing a database error safely — the savepoint every ``except`` needs.

The bug this exists to stop (G3)
--------------------------------
PostgreSQL aborts the WHOLE transaction on any statement error. Catching the
Python exception does not undo that: the connection stays in
``InFailedSqlTransaction`` and every later statement fails with
``current transaction is aborted, commands ignored until end of transaction
block``. So this shape ::

    try:
        SomeModel.objects.filter(...).delete()
    except Exception:
        pass                       # <-- looks harmless, poisons the transaction

turns ONE recoverable failure into a total loss of everything that follows, and
reports success while doing it. It bit a real provisioning drive: a query against
a tenant-only table issued from ``public`` failed, the handler swallowed it, and
every subsequent step in the drive failed for a reason that had nothing to do
with the step.

SQLite is far more forgiving, which is exactly why this class of bug survives a
green test suite and only shows up on production-parity Postgres.

The fix is a SAVEPOINT. ``transaction.atomic()`` opens one when it is nested
inside another atomic block; rolling back to it discards the failed statement and
leaves the enclosing transaction usable. When there is no enclosing transaction
it starts (and rolls back) a real one, which is equally correct.

Usage::

    with savepoint_suppress(context="delete workflow runs") as outcome:
        deleted, _ = WorkflowRun.objects.filter(school_id=sid).delete()
    if not outcome.ok:
        ...                        # the failure is visible, not invented away

Suppressing is still a decision. Use this where continuing is genuinely correct
(best-effort cleanup, optional telemetry); do not use it to hide a failure the
caller needs to know about — ``outcome`` exists so the caller can tell.
"""
from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass, field
from typing import Any

from django.db import DatabaseError, transaction

logger = logging.getLogger(__name__)

__all__ = ["SuppressedOutcome", "savepoint_suppress", "savepoint_call"]


@dataclass
class SuppressedOutcome:
    """What happened inside the block. Truthy when the block completed."""

    ok: bool = True
    error: BaseException | None = None
    context: str = ""
    result: Any = field(default=None)

    def __bool__(self) -> bool:
        return self.ok


@contextlib.contextmanager
def savepoint_suppress(
    *exceptions: type[BaseException],
    using: str | None = None,
    context: str = "",
    reraise: bool = False,
):
    """Run a database block inside its own savepoint, suppressing failures.

    Defaults to ``DatabaseError``, which is the family that poisons a Postgres
    transaction. Pass explicit types to widen it — but prefer the narrowest set
    that the block can genuinely raise.
    """
    caught = exceptions or (DatabaseError,)
    outcome = SuppressedOutcome(context=context)
    try:
        with transaction.atomic(using=using):
            yield outcome
    except caught as exc:  # noqa: B902 - the caller chose this set deliberately
        outcome.ok = False
        outcome.error = exc
        logger.warning(
            "Suppressed %s during %s (rolled back to savepoint, transaction "
            "still usable): %s",
            type(exc).__name__,
            context or "database block",
            exc,
        )
        if reraise:
            raise


def savepoint_call(func, *args, using: str | None = None, context: str = "", default=None, **kwargs):
    """Call ``func`` inside a savepoint; return its result, or ``default`` on failure.

    The function form for the very common one-liner case.
    """
    with savepoint_suppress(using=using, context=context or getattr(func, "__name__", "")) as outcome:
        outcome.result = func(*args, **kwargs)
    return outcome.result if outcome.ok else default
