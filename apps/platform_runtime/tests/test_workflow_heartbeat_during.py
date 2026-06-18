"""heartbeat_during(): keep a long blocking step's run alive so a healthy-but-slow
operation (e.g. a fresh tenant-schema migrate) is not false-flagged "abandoned: no
heartbeat past the stuck threshold".

The daemon-thread heartbeat writes from its OWN DB connection, which under the
in-memory SQLite test runner is a separate empty database — so these tests assert
the *mechanism* (the daemon pings heartbeat() on schedule while the block runs)
rather than cross-connection row visibility. A direct same-connection test proves
the underlying heartbeat() write itself. Production (shared postgres connection)
visibility is exercised by the provisioning integration path.
"""

from __future__ import annotations

import time
from unittest import mock

from django.test import TestCase

from apps.platform_runtime import workflow_tracker
from apps.platform_runtime.models import WorkflowRun
from apps.platform_runtime.workflow_tracker import (
    begin_run,
    heartbeat,
    heartbeat_during,
)


class HeartbeatDuringTests(TestCase):
    def _run(self):
        return begin_run(
            workflow_key="test_heartbeat_during",
            steps=("a", "b"),
            school_id="hb-test",
            expected_duration_seconds=600,
            payload={},
        )

    def test_fast_op_spawns_no_heartbeat(self):
        run = self._run()
        with mock.patch.object(workflow_tracker, "heartbeat") as beat:
            # Op finishes well within the interval → the daemon never pings.
            with heartbeat_during(run, interval_seconds=5.0):
                pass
        self.assertEqual(beat.call_count, 0)

    def test_slow_op_pings_heartbeat_on_schedule(self):
        run = self._run()
        with mock.patch.object(workflow_tracker, "heartbeat") as beat:
            # Op outlasts the interval → at least one ping must land while blocked.
            with heartbeat_during(run, interval_seconds=0.2):
                time.sleep(0.55)
        self.assertGreaterEqual(beat.call_count, 1)

    def test_exception_in_block_propagates_and_stops_thread(self):
        run = self._run()
        with mock.patch.object(workflow_tracker, "heartbeat"):
            with self.assertRaises(ValueError):
                with heartbeat_during(run, interval_seconds=0.2):
                    raise ValueError("boom")
        # The wrapped op's exception propagates unchanged; context exit must not hang.

    def test_none_run_is_a_safe_noop(self):
        # Defensive: a missing run must never raise or spawn a thread.
        with mock.patch.object(workflow_tracker, "heartbeat") as beat:
            with heartbeat_during(None, interval_seconds=0.1):
                pass
        self.assertEqual(beat.call_count, 0)

    def test_heartbeat_write_advances_last_heartbeat_at(self):
        # Same-connection proof the underlying write the daemon performs actually
        # advances last_heartbeat_at (backend-agnostic — no cross-thread DB).
        run = self._run()
        before = WorkflowRun.objects.get(pk=run.pk).last_heartbeat_at
        time.sleep(0.01)
        heartbeat(run)
        after = WorkflowRun.objects.get(pk=run.pk).last_heartbeat_at
        self.assertGreater(after, before)
