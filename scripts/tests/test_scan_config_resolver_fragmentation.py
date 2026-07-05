"""Unit tests for scripts/scan_config_resolver_fragmentation.py (stdlib, no Django).

Locks the ratchet's core semantics so the config-SOT freeze cannot silently
rot: fragmented-reader detection (Name + Attribute call forms), SOT-module and
tests/migrations exemptions, the allow-marker, canonical-reader passthrough,
services/ coverage, and the line-insensitive (path, name) multiset used by
--compare (line drift never trips; one MORE raw read in a file does).
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import scan_config_resolver_fragmentation as m  # noqa: E402


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class ScanTempTreeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._old_root = m.ROOT
        m.ROOT = self.root

    def tearDown(self):
        m.ROOT = self._old_root
        self._tmp.cleanup()

    def _scan(self):
        return m.scan()

    def test_flags_raw_namespace_read_in_consumer(self):
        _write(
            self.root,
            "apps/finance/views.py",
            "from apps.platform_runtime.helpers import get_effective_site_settings\n"
            "def v(request):\n"
            "    site = get_effective_site_settings(request=request)\n"
            "    return site.currency\n",
        )
        findings = self._scan()
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["name"], "get_effective_site_settings")
        self.assertEqual(findings[0]["path"], "apps/finance/views.py")

    def test_flags_all_three_fragmented_readers_and_attribute_form(self):
        _write(
            self.root,
            "apps/reports/services.py",
            "from apps.platform_runtime import helpers\n"
            "def f(request):\n"
            "    a = helpers.get_effective_site_settings(request=request)\n"
            "    b = get_legacy_site_settings_compat(request=request)\n"
            "    c = get_platform_site_settings_record(create=False)\n"
            "    return a, b, c\n",
        )
        names = sorted(f["name"] for f in self._scan())
        self.assertEqual(
            names,
            [
                "get_effective_site_settings",
                "get_legacy_site_settings_compat",
                "get_platform_site_settings_record",
            ],
        )

    def test_canonical_readers_never_flagged(self):
        _write(
            self.root,
            "apps/finance/views.py",
            "from apps.platform_runtime.config_resolver import get_effective_config\n"
            "from apps.siteconfig.config_service import get_finance_config\n"
            "def v(request):\n"
            "    x = get_effective_config(request.school, 'currency', request=request)\n"
            "    y = get_finance_config(request=request)\n"
            "    return x, y\n",
        )
        self.assertEqual(self._scan(), [])

    def test_sot_modules_exempt(self):
        for rel in (
            "apps/platform_runtime/helpers.py",
            "apps/platform_runtime/config_resolver.py",
            "apps/platform_runtime/site_settings_read_access.py",
            "apps/siteconfig/config_service.py",
        ):
            _write(
                self.root,
                rel,
                "def w(request):\n"
                "    return get_effective_site_settings(request=request)\n",
            )
        self.assertEqual(self._scan(), [])

    def test_tests_and_migrations_skipped(self):
        body = "def t():\n    return get_effective_site_settings()\n"
        _write(self.root, "apps/finance/tests/test_x.py", body)
        _write(self.root, "apps/finance/migrations/0001_x.py", body)
        _write(self.root, "apps/finance/test_views.py", body)
        self.assertEqual(self._scan(), [])

    def test_allow_marker_same_line_and_line_above(self):
        _write(
            self.root,
            "apps/portal/views.py",
            "def v(request):\n"
            "    a = get_effective_site_settings(request=request)  # config-resolver-allow: multi-attr-fanout-frozen\n"
            "    # config-resolver-allow: write-path-singleton-persistence\n"
            "    b = get_platform_site_settings_record(create=True)\n"
            "    return a, b\n",
        )
        self.assertEqual(self._scan(), [])

    def test_services_root_scanned(self):
        _write(
            self.root,
            "services/ai_helpers.py",
            "def f(request):\n"
            "    return get_effective_site_settings(request=request)\n",
        )
        findings = self._scan()
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["path"], "services/ai_helpers.py")

    def test_syntax_error_file_skipped_not_fatal(self):
        _write(self.root, "apps/broken/views.py", "def broken(:\n")
        _write(
            self.root,
            "apps/ok/views.py",
            "def v(request):\n"
            "    return get_effective_site_settings(request=request)\n",
        )
        self.assertEqual(len(self._scan()), 1)


class MultisetCompareTest(unittest.TestCase):
    def test_line_drift_does_not_grow(self):
        base = [
            {"path": "apps/a.py", "name": "get_effective_site_settings", "line": 10},
        ]
        cur = [
            {"path": "apps/a.py", "name": "get_effective_site_settings", "line": 99},
        ]
        self.assertEqual(m._multiset(base), m._multiset(cur))

    def test_one_more_occurrence_grows(self):
        base = [
            {"path": "apps/a.py", "name": "get_effective_site_settings", "line": 10},
        ]
        cur = base + [
            {"path": "apps/a.py", "name": "get_effective_site_settings", "line": 20},
        ]
        base_counts = m._multiset(base)
        cur_counts = m._multiset(cur)
        grew = {
            k: v for k, v in cur_counts.items() if v > base_counts.get(k, 0)
        }
        self.assertEqual(
            grew, {"apps/a.py::get_effective_site_settings": 2}
        )

    def test_burndown_never_trips(self):
        base = [
            {"path": "apps/a.py", "name": "get_effective_site_settings", "line": 10},
            {"path": "apps/a.py", "name": "get_effective_site_settings", "line": 20},
        ]
        cur = base[:1]
        base_counts = m._multiset(base)
        cur_counts = m._multiset(cur)
        grew = {k: v for k, v in cur_counts.items() if v > base_counts.get(k, 0)}
        self.assertEqual(grew, {})


if __name__ == "__main__":
    unittest.main()
