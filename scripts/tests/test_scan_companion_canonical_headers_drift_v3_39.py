"""Stdlib unittest coverage for ``scan_companion_canonical_headers_drift``.

These tests exercise the scanner against synthetic inputs by monkey-
patching the module's path constants. They do NOT touch the real
working-tree files — those are exercised by the Django test
``apps/migration_cloud/tests/test_canonical_headers_consistency_v3_39.py``.

Six scenarios:

  1. ``test_identical_mirrors_pass`` — SOT + both mirrors aligned;
     scanner reports 0 unallowed drift.
  2. ``test_missing_domain_detected`` — mirror omits a domain present
     in the SOT.
  3. ``test_extra_domain_detected`` — mirror has a domain not present
     in the SOT.
  4. ``test_order_mismatch_detected`` — same column set, different
     order.
  5. ``test_column_set_mismatch_detected`` — different column sets
     (one column dropped from mirror).
  6. ``test_allow_marker_honored`` — `_canonical-headers-drift-allow`
     suppresses the drift for the named domain.
"""

from __future__ import annotations

import importlib
import json
import pathlib
import sys
import textwrap
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import scan_companion_canonical_headers_drift as scanner  # noqa: E402


SOT_SOURCE_TEMPLATE = textwrap.dedent(
    '''\
    """Synthetic SOT module."""
    from __future__ import annotations

    DOMAIN_CANONICAL_HEADERS: dict[str, set[str]] = {body}
    '''
)


def _write_sot(tmp: pathlib.Path, body: str) -> pathlib.Path:
    source = SOT_SOURCE_TEMPLATE.format(body=body)
    path = tmp / "runmycampus_canonical.py"
    path.write_text(source, encoding="utf-8")
    return path


def _write_json(tmp: pathlib.Path, name: str, data: dict[str, object]) -> pathlib.Path:
    path = tmp / name
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


class CanonicalHeadersDriftScannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_root = pathlib.Path(self._make_tmp())
        self._patched: list[tuple[str, object]] = []

    def _make_tmp(self) -> str:
        import tempfile

        d = tempfile.mkdtemp(prefix="canonical-headers-drift-test-")
        self.addCleanup(self._rmtree, d)
        return d

    @staticmethod
    def _rmtree(d: str) -> None:
        import shutil

        shutil.rmtree(d, ignore_errors=True)

    def _patch(self, name: str, value: object) -> None:
        original = getattr(scanner, name)
        self._patched.append((name, original))
        setattr(scanner, name, value)

    def tearDown(self) -> None:
        for name, value in reversed(self._patched):
            setattr(scanner, name, value)

    # ---- helpers -----------------------------------------------------

    def _setup(
        self,
        sot_body: str,
        tauri_data: dict[str, object],
        docker_data: dict[str, object],
    ) -> None:
        sot_path = _write_sot(self.tmp_root, sot_body)
        tauri_path = _write_json(self.tmp_root, "tauri.json", tauri_data)
        docker_path = _write_json(self.tmp_root, "docker.json", docker_data)
        self._patch("DJANGO_SOT_PATH", sot_path)
        self._patch("TAURI_MIRROR_PATH", tauri_path)
        self._patch("DOCKER_MIRROR_PATH", docker_path)
        # Use a fresh baseline path inside the tmp dir so the scanner
        # never reads or overwrites the real var/.
        self._patch("BASELINE_PATH", self.tmp_root / "baseline.json")

    # ---- tests -------------------------------------------------------

    def test_identical_mirrors_pass(self) -> None:
        self._setup(
            sot_body='{"students": {"id", "name"}, "staff": {"id", "email"}}',
            tauri_data={
                "students": ["id", "name"],
                "staff": ["id", "email"],
            },
            docker_data={
                "students": ["id", "name"],
                "staff": ["id", "email"],
            },
        )
        unallowed, rows = scanner.run()
        self.assertEqual(unallowed, 0)
        self.assertTrue(all(r["drift_kind"] == "identical" for r in rows))
        self.assertEqual(len(rows), 4)  # 2 domains x 2 mirrors

    def test_missing_domain_detected(self) -> None:
        self._setup(
            sot_body='{"students": {"id", "name"}, "staff": {"id", "email"}}',
            tauri_data={
                "students": ["id", "name"],
                # staff missing in tauri
            },
            docker_data={
                "students": ["id", "name"],
                "staff": ["id", "email"],
            },
        )
        unallowed, rows = scanner.run()
        self.assertEqual(unallowed, 1)
        bad = [r for r in rows if r["drift_kind"] != "identical"]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["drift_kind"], "missing-in-mirror")
        self.assertEqual(bad[0]["mirror"], "companion-tauri")
        self.assertEqual(bad[0]["domain"], "staff")

    def test_extra_domain_detected(self) -> None:
        self._setup(
            sot_body='{"students": {"id", "name"}}',
            tauri_data={
                "students": ["id", "name"],
                "ghost": ["a", "b"],
            },
            docker_data={
                "students": ["id", "name"],
            },
        )
        unallowed, rows = scanner.run()
        self.assertEqual(unallowed, 1)
        bad = [r for r in rows if r["drift_kind"] != "identical"]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["drift_kind"], "extra-in-mirror")
        self.assertEqual(bad[0]["domain"], "ghost")

    def test_order_mismatch_detected(self) -> None:
        # Source order in the set literal is (id, name). The mirror
        # has (name, id) — same set, different order. Order matters
        # for canonical-CSV canonicalization downstream.
        self._setup(
            sot_body='{"students": {"id", "name"}}',
            tauri_data={"students": ["name", "id"]},
            docker_data={"students": ["id", "name"]},
        )
        unallowed, rows = scanner.run()
        self.assertEqual(unallowed, 1)
        bad = [r for r in rows if r["drift_kind"] != "identical"]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["drift_kind"], "order-mismatch")
        self.assertEqual(bad[0]["mirror"], "companion-tauri")

    def test_column_set_mismatch_detected(self) -> None:
        self._setup(
            sot_body='{"students": {"id", "name", "email"}}',
            tauri_data={"students": ["id", "name"]},  # email dropped
            docker_data={"students": ["id", "name", "email"]},
        )
        unallowed, rows = scanner.run()
        self.assertEqual(unallowed, 1)
        bad = [r for r in rows if r["drift_kind"] != "identical"]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["drift_kind"], "column-set-mismatch")

    def test_allow_marker_honored(self) -> None:
        self._setup(
            sot_body='{"students": {"id", "name", "email"}}',
            tauri_data={
                "students": ["id", "name"],  # would be column-set-mismatch
                "_canonical-headers-drift-allow": {
                    "students": "deprecation window 2026-05-19 -- agent-3 wave"
                },
            },
            docker_data={"students": ["id", "name", "email"]},
        )
        unallowed, rows = scanner.run()
        self.assertEqual(unallowed, 0)
        allowed_rows = [r for r in rows if r["allowed"]]
        self.assertEqual(len(allowed_rows), 1)
        self.assertEqual(allowed_rows[0]["mirror"], "companion-tauri")
        self.assertEqual(allowed_rows[0]["domain"], "students")
        self.assertIn("deprecation window", allowed_rows[0]["allow_reason"])


if __name__ == "__main__":
    unittest.main()
