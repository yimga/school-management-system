#!/usr/bin/env python3
"""Tests for verify_companion_server_contract.

Two things are being locked here, and they fail differently:

  * the EXTRACTOR must see a path in every shape a client writes one, and must
    not invent paths out of prose. An extractor that silently sees nothing
    reports a clean contract for a client that is entirely broken -- the exact
    false zero this gate exists to make impossible.
  * the RATCHET must bite in both directions. A baseline that can only excuse
    is a mute button; this one also fails on an entry that has started to
    resolve, and on an entry with no written reason.

Stdlib only -- no Django import, so these run anywhere.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_SCRIPTS = os.path.dirname(_HERE)
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import verify_companion_server_contract as gate  # noqa: E402


class ExtractorTests(unittest.TestCase):
    def _paths(self, text: str) -> list:
        return [m.group(0) for m in gate.PATH_RE.finditer(text)]

    def test_plain_string_literal(self):
        self.assertIn(
            "/api/v1/migration/maa/text/",
            self._paths('const RMC_MAA_TEXT_PATH: &str = "/api/v1/migration/maa/text/";'),
        )

    def test_rust_format_string(self):
        self.assertIn(
            "/api/v1/migration/companion/upload/",
            self._paths('format!("{}/api/v1/migration/companion/upload/", server_url)'),
        )

    def test_python_fstring(self):
        self.assertIn(
            "/api/v1/migration/companion/upload/",
            self._paths('url = f"{server_url.rstrip(\'/\')}/api/v1/migration/companion/upload/"'),
        )

    def test_typescript_template_literal(self):
        found = self._paths(
            '`${serverUrl}/api/v1/migration/companion/server-pubkey/?tenant=${slug}`'
        )
        self.assertIn("/api/v1/migration/companion/server-pubkey/", found)

    def test_prose_ellipsis_is_not_a_path(self):
        # `TARGET: RunMyCampus's OWN ``/api/v1/...`` endpoints` is a real line in
        # companion-docker/app/rmc_handshake.py. Treating it as a path would put
        # a permanent phantom finding in the baseline.
        kept = [p for p in self._paths("targets the /api/v1/... endpoints") if "..." not in p]
        self.assertEqual(kept, [])

    def test_sibling_own_routes_are_not_rmc_paths(self):
        # The Docker appliance serves /handshake/login ITSELF. Resolving that
        # against this project's urlconfs would be a guaranteed false finding.
        self.assertEqual(self._paths('@app.post("/handshake/login")'), [])

    def test_placeholder_is_substituted_before_resolving(self):
        self.assertEqual(
            gate.PLACEHOLDER_RE.sub("1", "/api/v1/migration/receipts/<id>/"),
            "/api/v1/migration/receipts/1/",
        )


class CollectorTests(unittest.TestCase):
    def test_walks_siblings_and_skips_tests_and_vendor(self):
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "companion-tauri", "src")
            os.makedirs(src)
            with open(os.path.join(src, "main.ts"), "w", encoding="utf-8") as fh:
                fh.write('fetch("/api/v1/real/one/");')

            tests = os.path.join(root, "companion-tauri", "tests")
            os.makedirs(tests)
            with open(os.path.join(tests, "t.ts"), "w", encoding="utf-8") as fh:
                fh.write('fetch("/api/v1/fixture/only/");')

            vendor = os.path.join(root, "companion-tauri", "node_modules", "x")
            os.makedirs(vendor)
            with open(os.path.join(vendor, "v.js"), "w", encoding="utf-8") as fh:
                fh.write('fetch("/api/v1/vendor/thing/");')

            got = gate.collect_targets(root)

        self.assertIn("/api/v1/real/one/", got)
        self.assertNotIn("/api/v1/fixture/only/", got)
        self.assertNotIn("/api/v1/vendor/thing/", got)
        self.assertEqual(got["/api/v1/real/one/"], ["companion-tauri/src/main.ts"])

    def test_markdown_is_not_a_client(self):
        # The spec being right is not in question; the mount is. Scanning docs
        # would put aspirational paths in a gate about shipped code.
        with tempfile.TemporaryDirectory() as root:
            d = os.path.join(root, "companion-docker", "app")
            os.makedirs(d)
            with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as fh:
                fh.write("POST `/api/v1/planned/endpoint/`")
            self.assertEqual(gate.collect_targets(root), {})


class RatchetTests(unittest.TestCase):
    @staticmethod
    def _result(dead=(), live=()):
        d = {p: {"sources": ["companion-tauri/src/a.ts"], "urlconfs": []} for p in dead}
        l = {p: {"sources": ["companion-tauri/src/a.ts"], "urlconfs": ["config.urls"]}
             for p in live}
        return {"dead": d, "live": l, "targets": dict(d, **l)}

    def test_clean_tree_passes(self):
        v = gate.evaluate(self._result(live=["/api/v1/x/"]), {})
        self.assertTrue(v["ok"])

    def test_new_dead_path_fails(self):
        v = gate.evaluate(self._result(dead=["/api/v1/new/"]), {})
        self.assertFalse(v["ok"])
        self.assertIn("/api/v1/new/", v["new_dead"])

    def test_baselined_dead_path_passes_and_is_still_reported(self):
        base = {"/api/v1/known/": {"path": "/api/v1/known/", "reason": "not built yet"}}
        v = gate.evaluate(self._result(dead=["/api/v1/known/"]), base)
        self.assertTrue(v["ok"])
        # Passing is not the same as forgetting: it must still surface.
        self.assertIn("/api/v1/known/", v["known_dead"])

    def test_baseline_entry_that_now_resolves_fails(self):
        base = {"/api/v1/known/": {"path": "/api/v1/known/", "reason": "not built yet"}}
        v = gate.evaluate(self._result(live=["/api/v1/known/"]), base)
        self.assertFalse(v["ok"])
        self.assertEqual(v["stale_baseline"], ["/api/v1/known/"])

    def test_reasonless_baseline_entry_fails(self):
        for entry in ({"path": "/api/v1/known/"},
                      {"path": "/api/v1/known/", "reason": "   "}):
            with self.subTest(entry=entry):
                v = gate.evaluate(self._result(dead=["/api/v1/known/"]),
                                  {"/api/v1/known/": entry})
                self.assertFalse(v["ok"])
                self.assertEqual(v["reasonless_baseline"], ["/api/v1/known/"])


class SelfCheckTests(unittest.TestCase):
    def test_self_check_passes(self):
        self.assertEqual(gate.self_check(), 0)


class LiveTreeTests(unittest.TestCase):
    """Calibration against the real repository, not a synthetic tree."""

    def test_the_siblings_are_actually_scanned(self):
        # A zero over an empty corpus is not a zero. If this drops to nothing,
        # the extractor or the walk has broken and every later assertion about
        # "no new dead paths" is meaningless.
        targets = gate.collect_targets()
        self.assertGreaterEqual(
            len(targets), 5,
            "the companion siblings target at least five RMC server paths; "
            "finding fewer means the scan stopped working, not that the "
            "clients stopped calling",
        )

    def test_baseline_is_present_and_every_entry_carries_a_reason(self):
        self.assertTrue(os.path.isfile(gate.BASELINE_PATH), gate.BASELINE_PATH)
        with open(gate.BASELINE_PATH, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        entries = doc.get("known_dead", [])
        self.assertTrue(entries)
        for entry in entries:
            self.assertTrue(entry.get("path", "").startswith("/api/"), entry)
            self.assertTrue((entry.get("reason") or "").strip(), entry)
            self.assertGreater(len(entry["reason"]), 40, entry["path"])

    def test_every_baselined_path_is_still_targeted_by_a_client(self):
        # If a client stops calling a path, the baseline entry is dead weight
        # and should be deleted rather than left to look like outstanding work.
        targets = set(gate.collect_targets())
        with open(gate.BASELINE_PATH, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
        for entry in doc.get("known_dead", []):
            self.assertIn(entry["path"], targets, entry["path"])


if __name__ == "__main__":
    unittest.main()
