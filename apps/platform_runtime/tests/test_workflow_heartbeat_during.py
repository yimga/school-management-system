"""heartbeat_during(): keep a long blocking step's run alive so a healthy-but-slow
operation (e.g. a fresh tenant-schema migrate) is not false-flagged "abandoned: no
heartbeat past the stuck threshold"."""

from __future__ import annotations

import time

from django.test import TestCase

from apps.platform_runtime.models import WorkflowRun
from apps.platform_runtime.workflow_tracker import begin_run, heartbeat_during


class HeartbeatDuringTests(TestCase):
    def _run(self):
        return begin_run(
            workflow_key="test_heartbeat_during",
            steps=("a", "b"),
            school_id="hb-test",
            expected_duration_seconds=600,
            payload={},
        )

    def _heartbeat(self, run):
        return WorkflowRun.objects.get(pk=run.pk).last_heartbeat_at

    def test_fast_op_spawns_no_extra_heartbeat(self):
        run = self._run()
        before = self._heartbeat(run)
        # Op completes well within the interval → the daemon never pings.
        with heartbeat_during(run, interval_seconds=5.0):
            pass
        self.assertEqual(self._heartbeat(run), before)

    def test_slow_op_keeps_run_alive(self):
        run = self._run()
        before = self._heartbeat(run)
        # Op outlasts the interval → at least one ping must land.
        with heartbeat_during(run, interval_seconds=0.2):
            time.sleep(0.55)
        self.assertGreater(self._heartbeat(run), before)

    def test_exception_in_block_still_stops_the_thread(self):
        run = self._run()
        with self.assertRaises(ValueError):
            with heartbeat_during(run, interval_seconds=0.2):
                raise ValueError("boom")
        # The wrapped op's exception propagates unchanged; no hang on context exit.

    def test_none_run_is_a_safe_noop(self):
        # Defensive: a missing run must never raise or spawn a thread.
        with heartbeat_during(None, interval_seconds=0.1):
            pass
