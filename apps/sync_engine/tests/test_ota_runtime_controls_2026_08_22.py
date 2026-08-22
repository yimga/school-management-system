"""Quieting the box, and — the part that matters — bringing it back.

Every control here has a failure mode that is WORSE than the problem it solves, and each
test below pins the specific way that must not happen:

  * a write freeze that outlives the upgrade locks a school out of its own system;
  * a thaw that writes ``False`` pins the box OUT of a maintenance mode an operator turned
    on deliberately before the upgrade started;
  * a "reload" that silently does nothing is worse than one that says it did nothing,
    because the operator stops looking;
  * a reload that guesses at a PID kills a school's web server.

No database and no network: these are cache and process-control primitives.
"""
from __future__ import annotations

import os
import signal
import tempfile
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from apps.sync_engine import upgrade_runtime


class WriteFreezeTests(SimpleTestCase):
    """The freeze is installed where the EXISTING maintenance middleware already looks."""

    def setUp(self):
        super().setUp()
        upgrade_runtime.thaw_writes()

    def tearDown(self):
        upgrade_runtime.thaw_writes()
        super().tearDown()

    def test_freeze_then_thaw(self):
        self.assertFalse(upgrade_runtime.writes_frozen())
        self.assertTrue(upgrade_runtime.freeze_writes())
        self.assertTrue(upgrade_runtime.writes_frozen())
        self.assertTrue(upgrade_runtime.thaw_writes())
        self.assertFalse(upgrade_runtime.writes_frozen())

    def test_the_freeze_lands_on_the_key_the_maintenance_middleware_reads(self):
        """If this drifts, the freeze is a cache write nothing consults."""
        from apps.siteconfig.middleware.maintenance_mode import (
            CACHE_KEY,
            MaintenanceModeMiddleware,
        )
        from apps.siteconfig.cache_utils import tenant_cache_key

        upgrade_runtime.freeze_writes()
        self.assertEqual(
            cache.get(tenant_cache_key(CACHE_KEY, None)),
            {"maintenance_mode": True},
        )
        # And the middleware's own reader agrees, which is the property that matters.
        self.assertTrue(MaintenanceModeMiddleware._is_maintenance_enabled(None))

    def test_thaw_deletes_rather_than_writing_false(self):
        """Writing False would pin the box OUT of an operator's deliberate maintenance."""
        from apps.siteconfig.cache_utils import tenant_cache_key
        from apps.siteconfig.middleware.maintenance_mode import CACHE_KEY

        key = tenant_cache_key(CACHE_KEY, None)
        upgrade_runtime.freeze_writes()
        upgrade_runtime.thaw_writes()
        self.assertIsNone(
            cache.get(key),
            "thaw wrote a value instead of deleting the key; the database's own "
            "maintenance_mode would be shadowed until the TTL expired",
        )

    @override_settings(RMC_OTA_FREEZE_WRITES=False)
    def test_the_freeze_is_switchable_off(self):
        self.assertFalse(upgrade_runtime.freeze_writes())
        self.assertFalse(upgrade_runtime.writes_frozen())

    @override_settings(RMC_OTA_WRITE_FREEZE_TTL_SECONDS=5)
    def test_the_freeze_ttl_has_a_floor(self):
        """A freeze shorter than an upgrade would thaw mid-migration."""
        self.assertEqual(upgrade_runtime.freeze_ttl_seconds(), 60)

    @override_settings(RMC_OTA_WRITE_FREEZE_TTL_SECONDS=2400)
    def test_the_freeze_ttl_is_configurable_above_the_floor(self):
        self.assertEqual(upgrade_runtime.freeze_ttl_seconds(), 2400)

    def test_the_freeze_is_written_with_an_expiry(self):
        """Its whole job is to expire if this process never reaches the thaw."""
        with mock.patch.object(upgrade_runtime, "freeze_ttl_seconds", return_value=1):
            upgrade_runtime.freeze_writes()
            self.assertTrue(upgrade_runtime.writes_frozen())
            import time

            time.sleep(1.2)
            self.assertFalse(
                upgrade_runtime.writes_frozen(),
                "the freeze outlived its TTL — a dead upgrade would leave a school "
                "locked out of its own system indefinitely",
            )


class WorkerReloadTests(SimpleTestCase):
    """Configured paths reload; an unconfigured box says so instead of guessing."""

    @override_settings(RMC_OTA_WORKER_RELOAD_COMMAND="", RMC_OTA_WORKER_RELOAD_PIDFILE="")
    def test_unconfigured_reload_reports_rather_than_guessing_a_pid(self):
        outcome = upgrade_runtime.reload_workers()
        self.assertIn("NOT configured", outcome)
        self.assertIn("container restart", outcome)

    @override_settings(RMC_OTA_WORKER_RELOAD_PIDFILE="", RMC_OTA_WORKER_RELOAD_COMMAND="")
    def test_a_pidfile_that_cannot_be_read_is_reported_not_swallowed(self):
        missing = os.path.join(tempfile.gettempdir(), "rmc-ota-absent.pid")
        with override_settings(RMC_OTA_WORKER_RELOAD_PIDFILE=missing):
            outcome = upgrade_runtime.reload_workers()
        self.assertIn("unreadable pidfile", outcome)

    def test_a_configured_command_is_split_and_run_without_a_shell(self):
        """shell=True on an operator-supplied string is a command-injection hole."""
        with override_settings(RMC_OTA_WORKER_RELOAD_COMMAND="supervisorctl restart web"):
            with mock.patch.object(upgrade_runtime.subprocess, "run") as runner:
                runner.return_value = mock.Mock(returncode=0, stderr="")
                outcome = upgrade_runtime.reload_workers()

        argv = runner.call_args.args[0]
        self.assertEqual(argv, ["supervisorctl", "restart", "web"])
        self.assertNotIn("shell", runner.call_args.kwargs)
        self.assertIn("reload command ok", outcome)

    def test_a_failing_command_reports_its_exit_code(self):
        with override_settings(RMC_OTA_WORKER_RELOAD_COMMAND="/bin/false"):
            with mock.patch.object(upgrade_runtime.subprocess, "run") as runner:
                runner.return_value = mock.Mock(returncode=3, stderr="nope")
                outcome = upgrade_runtime.reload_workers()
        self.assertIn("exited 3", outcome)

    def test_a_readable_pidfile_is_signalled_with_hup(self):
        handle = tempfile.NamedTemporaryFile("w", suffix=".pid", delete=False)
        handle.write("4242")
        handle.close()
        with override_settings(RMC_OTA_WORKER_RELOAD_PIDFILE=handle.name, RMC_OTA_WORKER_RELOAD_COMMAND=""):
            with mock.patch.object(upgrade_runtime.os, "kill") as killer:
                with mock.patch.object(upgrade_runtime.signal, "SIGHUP", getattr(signal, "SIGHUP", 1), create=True):
                    outcome = upgrade_runtime.reload_workers()
        killer.assert_called_once()
        self.assertEqual(killer.call_args.args[0], 4242)
        self.assertIn("4242", outcome)


class BackgroundWorkerTests(SimpleTestCase):
    @override_settings(CELERY_BROKER_URL="", RMC_OTA_WORKER_PAUSE_COMMAND="")
    def test_no_broker_is_stated_not_faked(self):
        self.assertIn("no broker", upgrade_runtime.pause_workers())
        self.assertIn("no broker", upgrade_runtime.resume_workers())

    @override_settings(CELERY_BROKER_URL="redis://valkey:6379/1", RMC_OTA_WORKER_PAUSE_COMMAND="")
    def test_pause_cancels_the_consumer_rather_than_shutting_workers_down(self):
        """Shutdown abandons in-flight work; an upgrade must not lose a queued receipt."""
        control = mock.Mock()
        with mock.patch.object(upgrade_runtime, "_celery_control", return_value=control):
            outcome = upgrade_runtime.pause_workers()
        control.cancel_consumer.assert_called_once()
        control.broadcast.assert_not_called()
        self.assertIn("stop consuming", outcome)

    @override_settings(CELERY_BROKER_URL="redis://valkey:6379/1", RMC_OTA_WORKER_RESUME_COMMAND="")
    def test_resume_re_adds_the_consumer(self):
        control = mock.Mock()
        with mock.patch.object(upgrade_runtime, "_celery_control", return_value=control):
            outcome = upgrade_runtime.resume_workers()
        control.add_consumer.assert_called_once()
        self.assertIn("resumed", outcome)

    @override_settings(CELERY_BROKER_URL="redis://valkey:6379/1")
    def test_a_broker_that_refuses_is_reported_not_raised(self):
        control = mock.Mock()
        control.cancel_consumer.side_effect = OSError("broker down")
        with mock.patch.object(upgrade_runtime, "_celery_control", return_value=control):
            outcome = upgrade_runtime.pause_workers()
        self.assertIn("could not pause", outcome)


class UpgradeFailureReportingTests(SimpleTestCase):
    """A box nobody is standing next to must be able to say why it failed."""

    def setUp(self):
        super().setUp()
        from apps.sync_engine import upgrade_lock

        upgrade_lock.reset()

    def tearDown(self):
        from apps.sync_engine import upgrade_lock

        upgrade_lock.reset()
        super().tearDown()

    def test_a_recorded_failure_rides_the_next_ordinary_handshake(self):
        from apps.sync_engine import upgrade_lock
        from apps.sync_engine.edge_outbox import (
            SYNC_UPGRADE_FAILURE_HEADER,
            local_manifest_headers,
        )

        upgrade_lock.record_local_failure(
            target_hash="c" * 64, error="verify FAILED — static/js/bundles/dashboard.js"
        )
        headers = local_manifest_headers()
        self.assertIn(SYNC_UPGRADE_FAILURE_HEADER, headers)
        self.assertIn("verify FAILED", headers[SYNC_UPGRADE_FAILURE_HEADER])
        self.assertTrue(headers[SYNC_UPGRADE_FAILURE_HEADER].startswith("cccccccccccc:"))

    def test_the_failure_header_is_header_safe(self):
        """A header a proxy rejects reports nothing at all."""
        from apps.sync_engine import upgrade_lock
        from apps.sync_engine.edge_outbox import (
            SYNC_UPGRADE_FAILURE_HEADER,
            local_manifest_headers,
        )

        upgrade_lock.record_local_failure(
            target_hash="c" * 64,
            error="line one\nline two\ttab — em dash and a very long tail " + ("x" * 800),
        )
        value = local_manifest_headers()[SYNC_UPGRADE_FAILURE_HEADER]
        self.assertNotIn("\n", value)
        self.assertNotIn("\t", value)
        value.encode("latin-1")  # must not raise
        self.assertLessEqual(len(value), 320)

    def test_no_failure_means_no_header(self):
        from apps.sync_engine.edge_outbox import (
            SYNC_UPGRADE_FAILURE_HEADER,
            local_manifest_headers,
        )

        self.assertNotIn(SYNC_UPGRADE_FAILURE_HEADER, local_manifest_headers())

    def test_the_cloud_logs_a_reported_failure(self):
        from django.test import RequestFactory

        from apps.api.sync_bundle_api import _log_upgrade_failure
        from apps.sync_engine.edge_outbox import SYNC_UPGRADE_FAILURE_HEADER

        header = "HTTP_" + SYNC_UPGRADE_FAILURE_HEADER.upper().replace("-", "_")
        request = RequestFactory().get("/api/sync/bundle/download/", **{header: "abc: verify FAILED"})

        class _School:
            pk = 41

        with self.assertLogs("apps.api.sync_bundle_api", level="WARNING") as captured:
            _log_upgrade_failure(request, _School())
        self.assertTrue(any("verify FAILED" in line for line in captured.output))

    def test_a_request_without_the_header_logs_nothing(self):
        import logging

        from django.test import RequestFactory

        from apps.api.sync_bundle_api import _log_upgrade_failure

        class _School:
            pk = 41

        logger = logging.getLogger("apps.api.sync_bundle_api")
        with mock.patch.object(logger, "warning") as warn:
            _log_upgrade_failure(RequestFactory().get("/api/sync/bundle/download/"), _School())
        warn.assert_not_called()
