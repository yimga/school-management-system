"""The OTA pipeline can be fully present and deliver nothing.

Every wire this gate checks is invisible to every other gate in the repo: the modules
import, the reference-integrity family resolves every symbol, and the unit tests pass —
because nothing is broken, the code is simply never reached. These tests pin the two
shapes that matter: a wire that was CUT, and a wire that is present but cannot fail.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_GATE = Path(__file__).resolve().parents[1] / "verify_ota_pipeline_wiring.py"
_spec = importlib.util.spec_from_file_location("verify_ota_pipeline_wiring", _GATE)
gate = importlib.util.module_from_spec(_spec)
sys.modules["verify_ota_pipeline_wiring"] = gate
_spec.loader.exec_module(gate)


class LiveTreeTests(unittest.TestCase):
    """Calibration: the gate must be green on the tree it ships with."""

    def test_the_live_tree_is_fully_wired(self):
        broken = gate.find_broken_wires() + gate.find_silent_manifest_build()
        self.assertEqual(
            broken,
            [],
            "the OTA pipeline is disconnected on this tree: "
            + "; ".join(f"{f['wire']} in {f['path']}" for f in broken),
        )

    def test_every_required_wire_names_what_breaks(self):
        """A gate that says 'wire cut' without saying what it costs gets ignored."""
        for wire in gate.REQUIRED_WIRES:
            with self.subTest(wire=wire["wire"]):
                self.assertTrue(wire["breaks"].strip(), "wire has no consequence text")
                self.assertGreater(len(wire["breaks"]), 30, "consequence text is a placeholder")


class CutWireTests(unittest.TestCase):
    def setUp(self):
        self._real_read = gate._read

    def tearDown(self):
        gate._read = self._real_read

    def test_a_cut_wire_is_a_finding(self):
        gate._read = lambda rel: "" if rel == "deploy/selfhost/entrypoint.web.sh" else self._real_read(rel)
        findings = gate.find_broken_wires()
        self.assertTrue(
            any(f["wire"] == "box-apply-step" for f in findings),
            "removing edge_apply_upgrade from the entrypoint was not reported; a box "
            "would report drift forever and never apply anything",
        )

    def test_a_missing_file_is_a_finding_not_a_crash(self):
        gate._read = lambda rel: None if rel == "build.sh" else self._real_read(rel)
        findings = gate.find_broken_wires()
        self.assertTrue(any(f["kind"] == "file_missing" for f in findings))

    def test_an_unmounted_route_is_a_finding(self):
        gate._read = lambda rel: "" if rel == "apps/api/urls.py" else self._real_read(rel)
        wires = {f["wire"] for f in gate.find_broken_wires()}
        self.assertIn("upgrade-routes-mounted", wires)
        self.assertIn("upgrade-chunk-mounted", wires)


class SilentFailureTests(unittest.TestCase):
    """Present-but-cannot-fail is worse than absent, because absence is at least visible."""

    def setUp(self):
        self._real_read = gate._read

    def tearDown(self):
        gate._read = self._real_read

    def _build_sh(self, line: str):
        gate._read = lambda rel: line if rel == "build.sh" else self._real_read(rel)

    def test_or_echo_on_the_manifest_build_is_a_finding(self):
        self._build_sh('python3 manage.py generate_system_manifest --channel stable || echo "WARNING"')
        findings = gate.find_silent_manifest_build()
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["kind"], "silent_failure")

    def test_or_true_is_also_a_finding(self):
        self._build_sh("python3 manage.py generate_system_manifest --channel stable || true")
        self.assertEqual(len(gate.find_silent_manifest_build()), 1)

    def test_a_fatal_manifest_build_is_clean(self):
        self._build_sh("python3 manage.py generate_system_manifest --channel stable")
        self.assertEqual(gate.find_silent_manifest_build(), [])

    def test_an_unrelated_or_true_line_is_not_a_finding(self):
        """Only the manifest build line is held to this; the rest of build.sh is not ours."""
        self._build_sh("find . -name '*.pyc' -delete || true")
        self.assertEqual(gate.find_silent_manifest_build(), [])


class ExitCodeTests(unittest.TestCase):
    def test_payload_reports_a_finding_count(self):
        payload = gate._payload([])
        self.assertEqual(payload["finding_count"], 0)
        self.assertEqual(payload["gate"], "ota-pipeline-wiring")
        self.assertEqual(payload["wires_checked"], len(gate.REQUIRED_WIRES))


if __name__ == "__main__":
    unittest.main()
