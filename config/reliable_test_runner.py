"""
Serial Django test runner with explicit DB connection cleanup.

- Forces parallel=0 (no multiprocessing test pool).
- Closes all connections before/after the suite to avoid SQLite handle leaks on Windows.

Disable via env: RMC_RELIABLE_TEST_RUNNER=0
"""

from __future__ import annotations

from django.db import connections
from django.test.runner import DiscoverRunner


class ReliableDiscoverRunner(DiscoverRunner):
    """DiscoverRunner that always runs tests serially and closes SQLite handles aggressively."""

    def run_tests(self, test_labels, extra_tests=None, **kwargs):
        kwargs["parallel"] = 0
        connections.close_all()
        try:
            return super().run_tests(test_labels, extra_tests=extra_tests, **kwargs)
        finally:
            connections.close_all()

    def teardown_databases(self, old_config, **kwargs):
        try:
            return super().teardown_databases(old_config, **kwargs)
        finally:
            connections.close_all()
