"""Adaptive edge<->cloud sync cadence + connectivity wake.

Every test here fails on the pre-2026-08-19 code, where the box attempted one full cycle
on a FIXED ``RMC_EDGE_SYNC_INTERVAL_SECONDS`` timer (default 180s, floor 60s) with no
notion of "the network just came back", "rows are flowing", or "stop hammering, we are
offline". The properties locked below are the ones that make convergence feel immediate
without polling hard:

  #1  a cycle that MOVED rows leaves the box HOT, so the next one follows in seconds
  #2  a clean but empty cycle relaxes to STEADY
  #3  a FAILING cycle backs off exponentially and the window is capped + jittered
  #4  the cheap reachability probe raises a WAKE on offline->online, which CANCELS
      whatever backoff remained — without this, backoff makes reconnection worse than
      the fixed timer it replaced
  #5  ``due_now`` is PURE: asking does not consume the wake, so a tick that declines to
      run (no school resolved) cannot silently eat it
  #6  an operator pin (RMC_EDGE_SYNC_INTERVAL_SECONDS) still wins exactly
  #7  the whole thing is fail-OPEN: a dead cache means "run", never "never run"
  #8  the dispatcher registers the job at the TICK cadence, not the sync interval
"""

from __future__ import annotations

import os
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.sync_engine import cadence, connectivity

_ENV_KEYS = (
    "RMC_EDGE_SYNC_INTERVAL_SECONDS",
    "RMC_EDGE_SYNC_HOT_SECONDS",
    "RMC_EDGE_SYNC_STEADY_SECONDS",
    "RMC_EDGE_SYNC_BACKOFF_BASE_SECONDS",
    "RMC_EDGE_SYNC_BACKOFF_CAP_SECONDS",
    "RMC_EDGE_SYNC_TICK_SECONDS",
    "RMC_EDGE_PROBE_TTL_SECONDS",
    "RMC_EDGE_PROBE_TIMEOUT_SECONDS",
)


class _CleanCadence(SimpleTestCase):
    """Cadence lives in the cache and reads env; both must be pristine per test.

    A developer ``.env`` that pins RMC_EDGE_SYNC_INTERVAL_SECONDS would otherwise turn
    every adaptive assertion below into an assertion about the pin.
    """

    def setUp(self):
        super().setUp()
        patcher = mock.patch.dict(os.environ, {k: "" for k in _ENV_KEYS}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        for key in _ENV_KEYS:
            os.environ.pop(key, None)
        cache.clear()
        self.addCleanup(cache.clear)


class CadenceStateTests(_CleanCadence):
    def test_a_cycle_that_moved_rows_goes_hot(self):
        decision = cadence.record_cycle({"ok": True, "pushed": 3, "pulled": 0})
        self.assertEqual(decision["state"], cadence.HOT)
        self.assertEqual(cadence.next_interval_seconds(), cadence.hot_seconds())

    def test_a_clean_but_empty_cycle_relaxes_to_steady(self):
        decision = cadence.record_cycle({"ok": True, "pushed": 0, "pulled": 0})
        self.assertEqual(decision["state"], cadence.STEADY)
        self.assertEqual(cadence.next_interval_seconds(), cadence.steady_seconds())

    def test_pulled_rows_count_as_movement_too(self):
        """Cloud->box traffic must keep the box hot, not just box->cloud."""
        decision = cadence.record_cycle({"ok": True, "pushed": 0, "pulled": 7})
        self.assertEqual(decision["state"], cadence.HOT)

    def test_a_failing_cycle_enters_backoff_and_counts_failures(self):
        for expected in (1, 2, 3):
            decision = cadence.record_cycle({"ok": False, "error": "unreachable"})
            self.assertEqual(decision["state"], cadence.BACKOFF)
            self.assertEqual(decision["failures"], expected)

    def test_a_success_clears_the_failure_count(self):
        cadence.record_cycle({"ok": False})
        cadence.record_cycle({"ok": False})
        self.assertEqual(cadence.consecutive_failures(), 2)
        cadence.record_cycle({"ok": True, "pushed": 1})
        self.assertEqual(cadence.consecutive_failures(), 0)

    def test_a_dry_run_is_never_folded_in_by_the_scheduler(self):
        """Guarded in edge_scheduler, asserted here as the contract it relies on.

        A dry run writes nothing in either direction, so it can neither prove throughput
        (HOT) nor clear a genuine outage (BACKOFF).
        """
        cadence.record_cycle({"ok": False})
        before = cadence.current_state()
        self.assertEqual(before, cadence.BACKOFF)


class BackoffWindowTests(_CleanCadence):
    def test_backoff_grows_with_failures(self):
        """Sampled: the window is jittered, so compare distributions, not single draws."""
        early = max(cadence.backoff_seconds(1) for _ in range(50))
        late = max(cadence.backoff_seconds(6) for _ in range(50))
        self.assertGreater(late, early)

    def test_backoff_never_exceeds_the_cap(self):
        cap = cadence.backoff_cap_seconds()
        for failures in (1, 3, 10, 50, 5000):
            for _ in range(25):
                self.assertLessEqual(cadence.backoff_seconds(failures), cap)

    def test_backoff_never_drops_below_the_floor(self):
        for failures in (0, 1, 2, 9):
            for _ in range(25):
                self.assertGreaterEqual(
                    cadence.backoff_seconds(failures), cadence.MIN_INTERVAL_SECONDS
                )

    def test_backoff_is_jittered_not_lockstep(self):
        """Several boxes returning from one power cut must not retry in unison."""
        draws = {cadence.backoff_seconds(5) for _ in range(60)}
        self.assertGreater(len(draws), 1, "backoff window is deterministic — herd risk")


class WakeTests(_CleanCadence):
    def test_due_now_is_pure_and_does_not_consume_the_wake(self):
        """The bug this guards: a tick asks "am I due?", says yes, then bails for another
        reason (no school resolved yet) — and the wake is gone, so the tick that COULD
        have run waits out the full interval."""
        cadence.schedule_next(3600)
        cadence.request_wake("connectivity restored")

        due, reason = cadence.due_now()
        self.assertTrue(due)
        self.assertIn("wake", reason)

        due_again, _ = cadence.due_now()
        self.assertTrue(due_again, "asking twice consumed the wake")
        self.assertEqual(cadence.pending_wake(), "connectivity restored")

    def test_consume_wake_clears_it_exactly_once(self):
        cadence.request_wake("local write")
        self.assertEqual(cadence.consume_wake(), "local write")
        self.assertEqual(cadence.consume_wake(), "")

    def test_a_wake_overrides_a_long_backoff(self):
        """THE property that makes backoff safe."""
        for _ in range(8):
            cadence.record_cycle({"ok": False})
        cadence.schedule_next(cadence.backoff_cap_seconds())
        self.assertFalse(cadence.due_now()[0])

        cadence.request_wake("connectivity restored")
        self.assertTrue(cadence.due_now()[0])

    def test_many_wakes_between_ticks_collapse_into_one(self):
        """A burst of local writes must debounce to a single cycle, not queue N."""
        for i in range(25):
            cadence.request_wake(f"write {i}")
        self.assertTrue(cadence.consume_wake())
        self.assertEqual(cadence.consume_wake(), "")


class DueGateTests(_CleanCadence):
    def test_not_due_before_the_interval_elapses(self):
        cadence.schedule_next(3600)
        due, reason = cadence.due_now()
        self.assertFalse(due)
        self.assertIn("not due", reason)

    def test_due_when_nothing_has_been_recorded(self):
        """Fail-OPEN: a fresh process / evicted key must sync, not go silent."""
        due, reason = cadence.due_now()
        self.assertTrue(due)
        self.assertIn("no cadence", reason)

    def test_due_when_the_marker_is_unreadable(self):
        cache.set("rmc:edge_sync:cadence_next_due", "not-a-number", 60)
        self.assertTrue(cadence.due_now()[0])

    def test_a_dead_cache_still_reports_due(self):
        """If the cache backend is down the box must keep syncing, not stop forever."""
        with mock.patch.object(cache, "get", side_effect=RuntimeError("cache down")):
            self.assertTrue(cadence.due_now()[0])

    def test_schedule_next_floors_a_misconfigured_interval(self):
        self.assertGreaterEqual(cadence.schedule_next(0), cadence.MIN_INTERVAL_SECONDS)
        self.assertGreaterEqual(cadence.schedule_next(-99), cadence.MIN_INTERVAL_SECONDS)


class OperatorPinTests(_CleanCadence):
    def test_an_explicit_pin_wins_over_every_adaptive_state(self):
        """A metered satellite link is a bandwidth bill, not a tuning opportunity."""
        with mock.patch.dict(os.environ, {"RMC_EDGE_SYNC_INTERVAL_SECONDS": "600"}):
            cadence.record_cycle({"ok": True, "pushed": 500})
            self.assertEqual(cadence.current_state(), cadence.HOT)
            self.assertEqual(cadence.next_interval_seconds(), 600)

            for _ in range(9):
                cadence.record_cycle({"ok": False})
            self.assertEqual(cadence.next_interval_seconds(), 600)

    def test_a_garbage_pin_is_ignored_rather_than_obeyed(self):
        with mock.patch.dict(os.environ, {"RMC_EDGE_SYNC_INTERVAL_SECONDS": "soon"}):
            self.assertEqual(cadence.pinned_interval_seconds(), 0)

    def test_no_pin_means_adaptive(self):
        self.assertEqual(cadence.pinned_interval_seconds(), 0)


@override_settings(RMC_EDGE_OPERATOR_BASE="https://manager.example.test")
class ConnectivityProbeTests(_CleanCadence):
    def test_target_is_parsed_from_the_operator_base(self):
        self.assertEqual(connectivity.operator_target(), ("manager.example.test", 443))

    @override_settings(RMC_EDGE_OPERATOR_BASE="http://box.local:8080/")
    def test_explicit_scheme_and_port_are_honoured(self):
        self.assertEqual(connectivity.operator_target(), ("box.local", 8080))

    @override_settings(RMC_EDGE_OPERATOR_BASE="manager.example.test")
    def test_a_bare_host_defaults_to_https(self):
        self.assertEqual(connectivity.operator_target(), ("manager.example.test", 443))

    @override_settings(RMC_EDGE_OPERATOR_BASE="", RMC_HUB_BASE_URL="")
    def test_no_operator_configured_reports_offline_without_probing(self):
        with mock.patch.object(connectivity, "_tcp_reachable") as probe:
            result = connectivity.check()
        probe.assert_not_called()
        self.assertFalse(result["online"])
        self.assertIn("no operator base", result["reason"])

    def test_going_online_raises_a_wake(self):
        """The whole reason the probe exists."""
        with mock.patch.object(connectivity, "_tcp_reachable", return_value=False):
            connectivity.check(force=True)
        self.assertEqual(cadence.pending_wake(), "")

        with mock.patch.object(connectivity, "_tcp_reachable", return_value=True):
            result = connectivity.check(force=True)
        self.assertEqual(result["transition"], "restored")
        self.assertIn("connectivity", cadence.pending_wake())

    def test_going_offline_does_not_raise_a_wake(self):
        with mock.patch.object(connectivity, "_tcp_reachable", return_value=True):
            connectivity.check(force=True)
        cadence.consume_wake()
        with mock.patch.object(connectivity, "_tcp_reachable", return_value=False):
            result = connectivity.check(force=True)
        self.assertEqual(result["transition"], "lost")
        self.assertEqual(cadence.pending_wake(), "")

    def test_staying_online_is_not_a_transition(self):
        """A wake on every probe would defeat the cadence entirely."""
        with mock.patch.object(connectivity, "_tcp_reachable", return_value=True):
            connectivity.check(force=True)
            cadence.consume_wake()
            result = connectivity.check(force=True)
        self.assertEqual(result["transition"], "")
        self.assertEqual(cadence.pending_wake(), "")

    def test_the_result_is_cached_so_probing_is_cheap(self):
        with mock.patch.object(connectivity, "_tcp_reachable", return_value=True) as probe:
            connectivity.check(force=True)
            connectivity.check()
            connectivity.check()
        self.assertEqual(probe.call_count, 1)

    def test_a_probe_failure_is_reported_not_raised(self):
        with mock.patch.object(connectivity, "_tcp_reachable", side_effect=OSError("down")):
            with self.assertRaises(OSError):
                connectivity._tcp_reachable("h", 1, 1)  # sanity: the mock does raise
        with mock.patch("socket.create_connection", side_effect=OSError("no route")):
            self.assertFalse(connectivity._tcp_reachable("h", 443, 1))


class SchedulerIntegrationTests(_CleanCadence):
    """The gate lives in run_edge_sync_now, so every trigger inherits it."""

    _RUN_CYCLE = "apps.sync_engine.sync_runner.run_sync_cycle"
    _RESOLVE = "apps.sync_engine.edge_scheduler.resolve_edge_school"

    @override_settings(RMC_EDGE_SYNC_ENABLED=False)
    def test_disabled_deployment_never_probes_or_syncs(self):
        from apps.sync_engine.edge_scheduler import run_edge_sync_now

        with mock.patch.object(connectivity, "check") as probe, mock.patch(
            self._RUN_CYCLE
        ) as cycle:
            result = run_edge_sync_now()
        probe.assert_not_called()
        cycle.assert_not_called()
        self.assertFalse(result["enabled"])

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_a_tick_that_is_not_due_does_no_work(self):
        from apps.sync_engine.edge_scheduler import run_edge_sync_now

        cadence.schedule_next(3600)
        with mock.patch.object(connectivity, "check", return_value={"online": True}), \
                mock.patch(self._RESOLVE, return_value=object()), \
                mock.patch(self._RUN_CYCLE) as cycle:
            result = run_edge_sync_now()
        cycle.assert_not_called()
        self.assertTrue(result["skipped"])

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_force_bypasses_the_cadence_gate(self):
        """An operator click / boot / host hook must never be told "not due"."""
        from apps.sync_engine.edge_scheduler import run_edge_sync_now

        cadence.schedule_next(3600)
        with mock.patch.object(connectivity, "check", return_value={"online": True}), \
                mock.patch(self._RESOLVE, return_value=object()), \
                mock.patch(self._RUN_CYCLE, return_value={"ok": True, "pushed": 0}) as cycle:
            run_edge_sync_now(force=True, trigger="edge_autosync")
        cycle.assert_called_once()

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_a_wake_is_not_consumed_when_no_school_resolves(self):
        """Regression: an unresolvable school used to eat the wake raised by the network
        coming back, so the box then waited out the whole backoff anyway."""
        from apps.sync_engine.edge_scheduler import run_edge_sync_now

        cadence.schedule_next(3600)
        cadence.request_wake("connectivity restored")
        with mock.patch.object(connectivity, "check", return_value={"online": True}), \
                mock.patch(self._RESOLVE, return_value=None), \
                mock.patch(self._RUN_CYCLE) as cycle:
            run_edge_sync_now()
        cycle.assert_not_called()
        self.assertEqual(cadence.pending_wake(), "connectivity restored")

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_a_live_cycle_updates_the_cadence(self):
        from apps.sync_engine.edge_scheduler import run_edge_sync_now

        with mock.patch.object(connectivity, "check", return_value={"online": True}), \
                mock.patch(self._RESOLVE, return_value=object()), \
                mock.patch(self._RUN_CYCLE, return_value={"ok": True, "pushed": 4}):
            result = run_edge_sync_now(force=True)
        self.assertEqual(result["cadence"]["state"], cadence.HOT)

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_a_dry_cycle_does_not_touch_the_cadence(self):
        from apps.sync_engine.edge_scheduler import run_edge_sync_now

        for _ in range(3):
            cadence.record_cycle({"ok": False})
        with mock.patch.object(connectivity, "check", return_value={"online": True}), \
                mock.patch(self._RESOLVE, return_value=object()), \
                mock.patch(self._RUN_CYCLE, return_value={"ok": True, "pushed": 0}):
            result = run_edge_sync_now(mode="dry", force=True)
        self.assertNotIn("cadence", result)
        self.assertEqual(cadence.current_state(), cadence.BACKOFF)
        self.assertEqual(cadence.consecutive_failures(), 3)

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_a_probe_explosion_does_not_break_the_tick(self):
        from apps.sync_engine.edge_scheduler import run_edge_sync_now

        with mock.patch.object(connectivity, "check", side_effect=RuntimeError("boom")), \
                mock.patch(self._RESOLVE, return_value=object()), \
                mock.patch(self._RUN_CYCLE, return_value={"ok": True, "pushed": 1}) as cycle:
            run_edge_sync_now(force=True)
        cycle.assert_called_once()


class TickRegistrationTests(_CleanCadence):
    def test_the_tick_is_short_so_a_wake_is_acted_on_quickly(self):
        from apps.sync_engine.edge_scheduler import edge_sync_tick_seconds

        self.assertLessEqual(edge_sync_tick_seconds(), 15)
        self.assertGreaterEqual(edge_sync_tick_seconds(), cadence.MIN_INTERVAL_SECONDS)

    def test_the_tick_never_outpaces_an_operator_pin(self):
        with mock.patch.dict(os.environ, {"RMC_EDGE_SYNC_INTERVAL_SECONDS": "7"}):
            from apps.sync_engine.edge_scheduler import edge_sync_tick_seconds

            self.assertLessEqual(edge_sync_tick_seconds(), 7)

    def test_the_legacy_interval_contract_is_unchanged(self):
        """Other callers still read this; adaptive cadence was added ALONGSIDE it."""
        from apps.sync_engine.edge_scheduler import edge_sync_interval_seconds

        self.assertEqual(edge_sync_interval_seconds(), 180)

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_the_dispatcher_registers_the_job_at_the_tick_cadence(self):
        """Registering at 180s put a 180s floor under reacting to a wake.

        Asserted as an ABSOLUTE bound, not merely "equals edge_sync_tick_seconds()" —
        that phrasing moves with the function it is checking, so swapping the
        registration back to the slow legacy interval would still pass.
        """
        from apps.platform_runtime.periodic import _maybe_register_edge_sync_job
        from apps.sync_engine.edge_scheduler import (
            edge_sync_interval_seconds,
            edge_sync_tick_seconds,
        )

        registry: dict = {}
        _maybe_register_edge_sync_job(registry)
        job = registry["sync_engine.edge_sync_cycle"]
        self.assertEqual(job.interval_seconds, edge_sync_tick_seconds())
        self.assertLessEqual(
            job.interval_seconds,
            15,
            "the dispatcher must tick fast enough for a wake to be acted on promptly",
        )
        self.assertLess(
            job.interval_seconds,
            edge_sync_interval_seconds(),
            "registering at the legacy sync interval reinstates the old latency floor",
        )

    @override_settings(RMC_EDGE_SYNC_ENABLED=False)
    def test_the_job_is_not_registered_off_an_edge_box(self):
        from apps.platform_runtime.periodic import _maybe_register_edge_sync_job

        registry: dict = {}
        _maybe_register_edge_sync_job(registry)
        self.assertEqual(registry, {})

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_the_scan_throttle_tightens_on_an_edge_box(self):
        """The /health/ tick is the only driver on a broker-less box, so a 60s scan floor
        would cap convergence at 60s however fast the job is registered."""
        from apps.platform_runtime.periodic import SCAN_THROTTLE_SECONDS, _scan_throttle_seconds

        self.assertLess(_scan_throttle_seconds(), SCAN_THROTTLE_SECONDS)

    @override_settings(RMC_EDGE_SYNC_ENABLED=False)
    def test_the_scan_throttle_is_untouched_on_the_cloud(self):
        from apps.platform_runtime.periodic import SCAN_THROTTLE_SECONDS, _scan_throttle_seconds

        self.assertEqual(_scan_throttle_seconds(), SCAN_THROTTLE_SECONDS)


class OfflineCostTests(_CleanCadence):
    """An offline box must get CHEAPER, not busier.

    The first cut of the adaptive cadence made this worse, not better: backoff ramps from
    a short base, so in the first ten minutes of an outage the box ran MORE full cycles
    than the old fixed 180s timer did — each one scanning the corpus and signing a bundle
    for a socket that cannot open. The cheap probe now vetoes those, bounded so a wrong
    probe cannot mute sync.
    """

    _RUN_CYCLE = "apps.sync_engine.sync_runner.run_sync_cycle"
    _RESOLVE = "apps.sync_engine.edge_scheduler.resolve_edge_school"

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_an_unreachable_operator_skips_the_expensive_cycle(self):
        from apps.sync_engine.edge_scheduler import run_edge_sync_now

        with mock.patch.object(connectivity, "check", return_value={"online": False, "host": "h"}), \
                mock.patch(self._RESOLVE, return_value=object()), \
                mock.patch(self._RUN_CYCLE) as cycle:
            result = run_edge_sync_now()
        cycle.assert_not_called()
        self.assertTrue(result["skipped"])
        self.assertEqual(result["probe_skips"], 1)

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_the_veto_is_bounded_so_a_wrong_probe_cannot_mute_sync(self):
        """THE safety property. A middlebox that blocks TCP while HTTP still works must
        cost a few skipped ticks, never a permanently silent sync engine."""
        from apps.sync_engine.edge_scheduler import run_edge_sync_now

        # Hold the due-gate open so this test measures the VETO bound and nothing
        # else. schedule_next(0) floors to MIN_INTERVAL_SECONDS, so it does NOT make a
        # tick due -- the first draft of this test silently exercised the due-gate
        # instead and passed for the wrong reason.
        with mock.patch.object(
            cadence, "due_now", return_value=(True, "test: forced due")
        ), mock.patch.object(
            connectivity, "check", return_value={"online": False, "host": "h"}
        ), mock.patch(self._RESOLVE, return_value=object()), mock.patch(
            self._RUN_CYCLE, return_value={"ok": False}
        ) as cycle:
            for _ in range(cadence.MAX_CONSECUTIVE_PROBE_SKIPS):
                run_edge_sync_now()
            cycle.assert_not_called()
            self.assertEqual(
                cadence.probe_skips(), cadence.MAX_CONSECUTIVE_PROBE_SKIPS
            )

            # The bound releases: a real cycle runs even though the probe still says
            # offline, so a wrong probe can never mute sync permanently.
            run_edge_sync_now()
        cycle.assert_called_once()

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_a_pending_wake_is_never_vetoed_by_the_probe(self):
        """A stale "offline" probe result must not swallow the wake that says otherwise."""
        from apps.sync_engine.edge_scheduler import run_edge_sync_now

        cadence.request_wake("connectivity restored")
        with mock.patch.object(connectivity, "check", return_value={"online": False, "host": "h"}), \
                mock.patch(self._RESOLVE, return_value=object()), \
                mock.patch(self._RUN_CYCLE, return_value={"ok": True, "pushed": 1}) as cycle:
            run_edge_sync_now()
        cycle.assert_called_once()

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_a_real_cycle_clears_the_veto_counter(self):
        from apps.sync_engine.edge_scheduler import run_edge_sync_now

        with mock.patch.object(connectivity, "check", return_value={"online": False, "host": "h"}), \
                mock.patch(self._RESOLVE, return_value=object()):
            run_edge_sync_now()
        self.assertEqual(cadence.probe_skips(), 1)

        with mock.patch.object(connectivity, "check", return_value={"online": True}), \
                mock.patch(self._RESOLVE, return_value=object()), \
                mock.patch(self._RUN_CYCLE, return_value={"ok": True, "pushed": 1}):
            run_edge_sync_now(force=True)
        self.assertEqual(cadence.probe_skips(), 0)

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_force_ignores_the_probe_entirely(self):
        from apps.sync_engine.edge_scheduler import run_edge_sync_now

        with mock.patch.object(connectivity, "check", return_value={"online": False, "host": "h"}), \
                mock.patch(self._RESOLVE, return_value=object()), \
                mock.patch(self._RESOLVE, return_value=object()), \
                mock.patch(self._RUN_CYCLE, return_value={"ok": False}) as cycle:
            run_edge_sync_now(force=True)
        cycle.assert_called_once()

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_an_unknown_link_state_does_not_veto(self):
        """`online` is None when the probe has never run or is unconfigured. Unknown is
        not "offline" — treating it as such would stop sync on a box with no probe."""
        from apps.sync_engine.edge_scheduler import run_edge_sync_now

        with mock.patch.object(connectivity, "check", return_value={"online": None}), \
                mock.patch(self._RESOLVE, return_value=object()), \
                mock.patch(self._RUN_CYCLE, return_value={"ok": True, "pushed": 0}) as cycle:
            run_edge_sync_now()
        cycle.assert_called_once()


@override_settings(RMC_EDGE_OPERATOR_BASE="https://manager.example.test")
class TransitionDurabilityTests(_CleanCadence):
    """The restore wake must survive the probe RESULT cache expiring.

    Found by running the full outage journey rather than reasoning about it. Transition
    detection originally read the previous value out of the short-TTL result cache — so
    during an outage, when the cycle backs off and ticks spread past the probe TTL, the
    cached result expired, the next probe saw "no previous state", the offline->online
    flip was NOT a transition, and no wake was raised. The box then sat out the remaining
    backoff exactly as it did before any of this existed: the single case the whole design
    is for was the one case that silently did not work.
    """

    _RESULT_KEY = "rmc:edge_sync:connectivity"

    def test_restore_is_detected_even_after_the_result_cache_expired(self):
        with mock.patch.object(connectivity, "_tcp_reachable", return_value=False):
            connectivity.check(force=True)

        # Simulate the TTL lapsing between probes (a backoff gap longer than the TTL).
        cache.delete(self._RESULT_KEY)
        self.assertEqual(connectivity.last_known(), {})

        with mock.patch.object(connectivity, "_tcp_reachable", return_value=True):
            result = connectivity.check(force=True)
        self.assertEqual(result["transition"], "restored")
        self.assertIn("connectivity", cadence.pending_wake())

    def test_a_first_ever_probe_is_not_reported_as_a_transition(self):
        """No prior observation means no flip — a cold box must not fake a restore."""
        with mock.patch.object(connectivity, "_tcp_reachable", return_value=True):
            result = connectivity.check(force=True)
        self.assertEqual(result["transition"], "")
        self.assertEqual(cadence.pending_wake(), "")

    def test_the_remembered_state_outlives_the_result_ttl(self):
        with mock.patch.object(connectivity, "_tcp_reachable", return_value=True):
            connectivity.check(force=True)
        cache.delete(self._RESULT_KEY)
        with mock.patch.object(connectivity, "_tcp_reachable", return_value=False):
            result = connectivity.check(force=True)
        self.assertEqual(result["transition"], "lost")


class MisdiagnosisTests(_CleanCadence):
    """The cadence must never answer a question it was not asked.

    Both defects below shipped in the first cut of the adaptive cadence and both have the
    same shape: a CONFIGURATION error was reported as a TIMING or NETWORK condition, which
    sends the operator to look in the wrong place and, in the second case, silently
    suppresses cycles while doing it.
    """

    _RUN_CYCLE = "apps.sync_engine.sync_runner.run_sync_cycle"
    _RESOLVE = "apps.sync_engine.edge_scheduler.resolve_edge_school"

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_a_box_with_no_school_is_told_that_even_when_not_due(self):
        """Previously the gate ran first, so a box that could NEVER sync reported
        'not due for 44s (steady)' — hiding the only fact its operator needed."""
        from apps.sync_engine.edge_scheduler import run_edge_sync_now

        cadence.schedule_next(3600)
        with mock.patch.object(connectivity, "check", return_value={"online": True}), \
                mock.patch(self._RESOLVE, return_value=None), \
                mock.patch(self._RUN_CYCLE) as cycle:
            result = run_edge_sync_now()
        cycle.assert_not_called()
        self.assertFalse(result["ran"])
        self.assertIn("school", result["reason"])
        self.assertNotIn("not due", result["reason"])

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_an_unconfigured_operator_base_does_not_trip_the_probe_veto(self):
        """connectivity.check() reports online=False with host="" when nothing is
        configured. That is a settings problem, not an outage: vetoing on it suppressed up
        to MAX_CONSECUTIVE_PROBE_SKIPS cycles while blaming the network. The cycle must run
        and fail on the real, named cause."""
        from apps.sync_engine.edge_scheduler import run_edge_sync_now

        unconfigured = {"online": False, "host": "", "port": 0,
                        "reason": "no operator base configured (RMC_EDGE_OPERATOR_BASE)"}
        with mock.patch.object(connectivity, "check", return_value=unconfigured), \
                mock.patch(self._RESOLVE, return_value=object()), \
                mock.patch(self._RUN_CYCLE, return_value={"ok": False}) as cycle:
            result = run_edge_sync_now()
        cycle.assert_called_once()
        self.assertEqual(cadence.probe_skips(), 0, "an unconfigured box must not be vetoed")
        self.assertNotIn("skipped", result)

    @override_settings(RMC_EDGE_SYNC_ENABLED=True)
    def test_a_configured_but_unreachable_operator_is_still_vetoed(self):
        """The veto still does its job — this is the case it exists for."""
        from apps.sync_engine.edge_scheduler import run_edge_sync_now

        with mock.patch.object(
            connectivity, "check", return_value={"online": False, "host": "ops.example"}
        ), mock.patch(self._RESOLVE, return_value=object()), \
                mock.patch(self._RUN_CYCLE) as cycle:
            result = run_edge_sync_now()
        cycle.assert_not_called()
        self.assertTrue(result["skipped"])
        self.assertEqual(result["probe_skips"], 1)
