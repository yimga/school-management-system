"""A cold cloud 502s everything. The box must not read that as a dead cloud.

MEASURED 2026-08-20 21:07 UTC against the production cloud, no deploy in flight:
every path returned 502 with ``x-render-routing: dynamic-paid-error`` — including
``/static/js/service-worker.js`` and ``/api/nonexistent-route-xyz/``. Sixty seconds
later all of them served correctly. A static asset cannot 502 from schema drift and
a nonexistent route cannot 502 from application code, so the service was COLD.

The consequence for sync is the whole reason this module exists: a box on a cadence
takes the 502 and records a failure, then a human opens a browser — warming the
service — and sees a healthy site. The failure is invisible from the only side that
looks.

The sharpest tests here are the NEGATIVE ones: a 4xx must NOT be retried. Retrying a
401 hammers the cloud with a credential that will never work, and retrying a 404
buries a path bug under latency.
"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.sync_engine.gateway_retry import (
    GATEWAY_STATUSES,
    call_with_gateway_retry,
    gateway_error_hint,
    is_gateway_error,
)


class IsGatewayErrorTests(SimpleTestCase):
    def test_the_three_gateway_statuses(self):
        for status in (502, 503, 504):
            self.assertTrue(is_gateway_error(status), status)

    def test_client_and_success_statuses_are_not_gateway_errors(self):
        for status in (200, 201, 204, 301, 400, 401, 403, 404, 409, 422, 500):
            self.assertFalse(is_gateway_error(status), status)

    def test_500_is_deliberately_excluded(self):
        """A 500 is the application answering. It is a bug report, not a cold start."""
        self.assertNotIn(500, GATEWAY_STATUSES)

    def test_junk_is_not_a_gateway_error(self):
        for junk in (None, "", "502x", object()):
            self.assertFalse(is_gateway_error(junk))

    def test_a_numeric_string_still_resolves(self):
        self.assertTrue(is_gateway_error("502"))


class RetryTests(SimpleTestCase):
    def _recorder(self):
        slept: list[float] = []
        return slept, slept.append

    def test_a_success_is_returned_without_retrying(self):
        calls = []

        def once():
            calls.append(1)
            return 200, "ok"

        slept, sleep = self._recorder()
        status, body = call_with_gateway_retry(once, sleep=sleep)
        self.assertEqual((status, body), (200, "ok"))
        self.assertEqual(len(calls), 1)
        self.assertEqual(slept, [])

    def test_a_cold_cloud_that_wakes_up_succeeds(self):
        """The exact production sequence: 502, then 200."""
        responses = [(502, "cold"), (200, "warm")]
        slept, sleep = self._recorder()
        status, body = call_with_gateway_retry(lambda: responses.pop(0), sleep=sleep)
        self.assertEqual((status, body), (200, "warm"))
        self.assertEqual(len(slept), 1, "must have waited exactly once")
        self.assertGreater(slept[0], 0)

    def test_a_401_is_never_retried(self):
        """The negative that matters. A refused credential will be refused again."""
        calls = []

        def refused():
            calls.append(1)
            return 401, "nope"

        slept, sleep = self._recorder()
        status, _ = call_with_gateway_retry(refused, sleep=sleep)
        self.assertEqual(status, 401)
        self.assertEqual(len(calls), 1)
        self.assertEqual(slept, [])

    def test_a_404_is_never_retried(self):
        """Retrying would hide a path bug behind latency — the /api/v1/ failure."""
        calls = []
        slept, sleep = self._recorder()
        status, _ = call_with_gateway_retry(
            lambda: (calls.append(1), (404, "<!doctype html>"))[1], sleep=sleep
        )
        self.assertEqual(status, 404)
        self.assertEqual(len(calls), 1)

    def test_a_cloud_that_is_genuinely_down_surfaces_its_502(self):
        """Retrying must not convert a real outage into something else."""
        calls = []
        slept, sleep = self._recorder()
        status, body = call_with_gateway_retry(
            lambda: (calls.append(1), (502, "down"))[1], attempts=3, sleep=sleep
        )
        self.assertEqual((status, body), (502, "down"))
        self.assertEqual(len(calls), 3, "all attempts used")
        self.assertEqual(len(slept), 2, "slept between attempts, not after the last")

    def test_attempts_of_one_disables_retrying(self):
        calls = []
        slept, sleep = self._recorder()
        call_with_gateway_retry(
            lambda: (calls.append(1), (502, ""))[1], attempts=1, sleep=sleep
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(slept, [])

    def test_backoff_grows(self):
        """A flat backoff either gives up too early or waits too long every time."""
        slept, sleep = self._recorder()
        call_with_gateway_retry(
            lambda: (503, ""), attempts=3, delays=[5.0, 20.0], sleep=sleep
        )
        self.assertEqual(slept, [5.0, 20.0])

    def test_a_failing_on_retry_callback_never_breaks_transport(self):
        responses = [(502, "cold"), (200, "warm")]

        def boom(_attempt, _total, _wait):
            raise RuntimeError("telemetry exploded")

        status, _ = call_with_gateway_retry(
            lambda: responses.pop(0), sleep=lambda _s: None, on_retry=boom
        )
        self.assertEqual(status, 200)

    def test_connectivity_failures_propagate_untouched(self):
        """An offline box must not spend its cycle sleeping; the caller queues instead."""

        def offline():
            raise OSError("network unreachable")

        with self.assertRaises(OSError):
            call_with_gateway_retry(offline, sleep=lambda _s: None)


class HintTests(SimpleTestCase):
    def test_the_hint_never_blames_the_operator_base(self):
        """Every message in this product used to, and it was never once the cause."""
        hint = gateway_error_hint(502)
        self.assertNotIn("RMC_EDGE_OPERATOR_BASE", hint)
        self.assertIn("not a box-side fault", hint)

    def test_the_hint_names_both_real_causes_and_what_to_run(self):
        hint = gateway_error_hint(503)
        self.assertIn("cold", hint)
        self.assertIn("missing a column", hint)
        self.assertIn("check_edge_sync_deploy_readiness", hint)

    def test_no_hint_for_a_status_that_is_not_a_gateway_error(self):
        self.assertEqual(gateway_error_hint(404), "")
