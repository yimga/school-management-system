"""Isolate the sync engine's CACHE-backed state between tests.

Django's ``TestCase`` rolls back the database between tests. It does not touch the cache,
and the adaptive cadence (``apps.sync_engine.cadence``) plus the connectivity probe
(``apps.sync_engine.connectivity``) keep their entire state there — next-due time, the
HOT/STEADY/BACKOFF phase, consecutive failures, the probe-skip counter, the pending wake,
and the durable last-observed link state.

That state therefore SURVIVES a test and leaks into the next one, which made the suite
order-dependent in a way that reads as a product bug: a test that legitimately expects
``run_edge_sync_now`` to run a cycle instead gets ``not due for 44s (steady)`` because
some earlier test left the box in STEADY with a recent cycle recorded. Two tests in
``test_edge_autosync_scheduling_2026_08_16.py`` were failing for exactly this reason, and
the failure had nothing to do with what they were testing.

Autouse so no test has to remember, and function-scoped so each test starts from a box
that has never synced. pytest applies autouse fixtures to ``unittest.TestCase`` subclasses
too, which is what every test in this package is.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_edge_sync_cache_state():
    """Clear cadence + connectivity state before AND after each test.

    Before, so a test never inherits a predecessor's cadence. After, so a test that
    deliberately drives the box into BACKOFF cannot poison an unrelated module later in
    the session.
    """

    def _clear():
        try:
            from apps.sync_engine import cadence

            cadence.reset()
        except Exception:  # noqa: BLE001 - never let isolation break collection
            pass
        try:
            from apps.sync_engine import connectivity

            connectivity.reset()
        except Exception:  # noqa: BLE001
            pass
        try:
            # The change beacon COALESCES writes in-process (one per school per half
            # second), and a rolled-back TestCase reuses primary keys — so without this a
            # school created in one test can inherit the previous test's coalescing
            # timestamp for the same pk and silently skip its beacon write.
            from apps.sync_engine import change_beacon

            change_beacon.reset()
        except Exception:  # noqa: BLE001
            pass
        try:
            # Sent-row memory for the push leg lives in the cache and would otherwise
            # suppress a legitimate delta in the next test.
            from apps.sync_engine import push_ledger

            push_ledger.reset()
        except Exception:  # noqa: BLE001
            pass

    _clear()
    yield
    _clear()
