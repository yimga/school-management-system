"""Loop watchdog + auto-remediate unit tests."""

from __future__ import annotations

import time
import unittest

from apps.migration_cloud.loop_watchdog import LoopWatchdog, SystemicStallError


class LoopWatchdogTests(unittest.TestCase):
    def test_advances_without_stall(self) -> None:
        with LoopWatchdog(max_stall_iterations=3, timeout_seconds=5.0) as wd:
            for i in range(5):
                wd.heartbeat(current_pointer=i, mutations_count=i * 2)

    def test_raises_after_repeated_stall(self) -> None:
        with LoopWatchdog(max_stall_iterations=2, timeout_seconds=30.0) as wd:
            wd.heartbeat(current_pointer=0, mutations_count=0)
            wd.heartbeat(current_pointer=0, mutations_count=0)
            with self.assertRaises(SystemicStallError):
                wd.heartbeat(current_pointer=0, mutations_count=0)

    def test_timeout_raises(self) -> None:
        wd = LoopWatchdog(max_stall_iterations=10, timeout_seconds=0.08)
        wd.heartbeat(current_pointer=0, mutations_count=0)
        time.sleep(0.12)
        with self.assertRaises(SystemicStallError):
            wd.heartbeat(current_pointer=0, mutations_count=0)


class AutoRemediateImportTests(unittest.TestCase):
    def test_auto_remediate_module_imports_with_django(self) -> None:
        import django
        from django.conf import settings

        if not settings.configured:
            django.setup()
        from apps.migration_cloud.auto_remediate import auto_remediate_before_repair

        self.assertTrue(callable(auto_remediate_before_repair))
