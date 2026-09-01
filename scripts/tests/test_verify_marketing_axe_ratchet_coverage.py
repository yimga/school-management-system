"""Stdlib unittest coverage for ``verify_marketing_axe_ratchet_coverage``.

The gate's whole job is to notice when the axe sweep stops scanning pages the
suite already believes are in scope. A gate that cannot be made to fail proves
nothing, so every case below drives the module against a synthetic tree with a
KNOWN defect and asserts it is reported — and one case runs against the real
tree, so a narrowed page list turns this red immediately.
"""

from __future__ import annotations

import contextlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import verify_marketing_axe_ratchet_coverage as v  # noqa: E402

GATE = SCRIPTS_DIR / "verify_marketing_axe_ratchet_coverage.py"

_SWEEP_TEMPLATE = """
const PAGES = [
{pages}
];
"""

_TRUTH_TEMPLATE = """
const PAGES = [
{pages}
];
"""

_A11Y_TEMPLATE = """
const ACCESSIBILITY_PATHS = [
{pages}
];
"""


def _lines(paths):
    return "\n".join(f'  "{p}",' for p in paths)


@contextlib.contextmanager
def _tree(sweep, truth, a11y, baseline=None, workflow=True):
    """Build a throwaway repo shaped like the real one and point the gate at it."""
    root = pathlib.Path(tempfile.mkdtemp(prefix="axe-ratchet-gate-"))
    try:
        (root / "scripts").mkdir()
        (root / "tests" / "e2e").mkdir(parents=True)
        (root / "var").mkdir()
        (root / ".github" / "workflows").mkdir(parents=True)
        (root / "scripts" / "run_marketing_axe_sweep.mjs").write_text(
            _SWEEP_TEMPLATE.format(pages=_lines(sweep)), encoding="utf-8"
        )
        (root / "tests" / "e2e" / "marketing-visual-truth.spec.js").write_text(
            _TRUTH_TEMPLATE.format(pages=_lines(truth)), encoding="utf-8"
        )
        (root / "tests" / "e2e" / "marketing-accessibility.spec.js").write_text(
            _A11Y_TEMPLATE.format(pages=_lines(a11y)), encoding="utf-8"
        )
        if baseline is not None:
            (root / "var" / "a11y-marketing-axe-baseline.json").write_text(
                json.dumps(baseline), encoding="utf-8"
            )
        if workflow:
            (root / ".github" / "workflows" / "marketing-axe-ratchet.yml").write_text(
                "run: bash scripts/run_marketing_axe_ratchet.sh\n", encoding="utf-8"
            )
        saved = (
            v.REPO_ROOT,
            v.SWEEP,
            v.BASELINE,
            v.VISUAL_TRUTH_SPEC,
            v.ACCESSIBILITY_SPEC,
            v.WORKFLOW_DIR,
        )
        v.REPO_ROOT = root
        v.SWEEP = root / "scripts" / "run_marketing_axe_sweep.mjs"
        v.BASELINE = root / "var" / "a11y-marketing-axe-baseline.json"
        v.VISUAL_TRUTH_SPEC = root / "tests" / "e2e" / "marketing-visual-truth.spec.js"
        v.ACCESSIBILITY_SPEC = root / "tests" / "e2e" / "marketing-accessibility.spec.js"
        v.WORKFLOW_DIR = root / ".github" / "workflows"
        try:
            yield root
        finally:
            (
                v.REPO_ROOT,
                v.SWEEP,
                v.BASELINE,
                v.VISUAL_TRUTH_SPEC,
                v.ACCESSIBILITY_SPEC,
                v.WORKFLOW_DIR,
            ) = saved
    finally:
        shutil.rmtree(root, ignore_errors=True)


_OK_BASELINE = {"max_failing_pages": 0, "allowed_contrast_pairs": []}


class CoverageGateTests(unittest.TestCase):
    def test_clean_tree_passes(self):
        with _tree(
            sweep=["/", "/pricing/", "/platform/analytics/"],
            truth=["/", "/pricing/"],
            a11y=["/", "/platform/analytics/"],
            baseline=_OK_BASELINE,
        ):
            self.assertEqual(v.main(), 0)

    def test_detects_a_narrowed_sweep(self):
        """The exact defect this gate exists for: the sweep drops a page the
        accessibility spec still covers. /platform/analytics/ was failing
        color-contrast at 1.08:1 while a sweep without it reported zero."""
        with _tree(
            sweep=["/", "/pricing/"],
            truth=["/", "/pricing/"],
            a11y=["/", "/platform/analytics/", "/platform/security/"],
            baseline=_OK_BASELINE,
        ):
            self.assertEqual(v.main(), 1)

    def test_detects_a_dropped_visual_truth_page(self):
        with _tree(
            sweep=["/"],
            truth=["/", "/why-switch/"],
            a11y=["/"],
            baseline=_OK_BASELINE,
        ):
            self.assertEqual(v.main(), 1)

    def test_marketing_home_alias_is_not_a_false_positive(self):
        """The accessibility spec navigates "/" as "/marketing/". Both name the
        same page and must not be reported as uncovered."""
        with _tree(
            sweep=["/"],
            truth=["/"],
            a11y=["/marketing/"],
            baseline=_OK_BASELINE,
        ):
            self.assertEqual(v.main(), 0)

    def test_missing_baseline_is_a_finding(self):
        with _tree(sweep=["/"], truth=["/"], a11y=["/"], baseline=None):
            self.assertEqual(v.main(), 1)

    def test_malformed_baseline_cap_is_a_finding(self):
        with _tree(
            sweep=["/"],
            truth=["/"],
            a11y=["/"],
            baseline={"max_failing_pages": "lots", "allowed_contrast_pairs": []},
        ):
            self.assertEqual(v.main(), 1)

    def test_malformed_pair_key_is_a_finding(self):
        with _tree(
            sweep=["/"],
            truth=["/"],
            a11y=["/"],
            baseline={
                "max_failing_pages": 0,
                "allowed_contrast_pairs": ["color-contrast on cream"],
            },
        ):
            self.assertEqual(v.main(), 1)

    def test_well_formed_pair_key_is_accepted(self):
        with _tree(
            sweep=["/"],
            truth=["/"],
            a11y=["/"],
            baseline={
                "max_failing_pages": 1,
                "allowed_contrast_pairs": ["color-contrast|#d4af37|#faf7f2"],
            },
        ):
            self.assertEqual(v.main(), 0)

    def test_unrun_ratchet_is_a_finding(self):
        """A ratchet no workflow invokes is a ratchet that never moves."""
        with _tree(
            sweep=["/"],
            truth=["/"],
            a11y=["/"],
            baseline=_OK_BASELINE,
            workflow=False,
        ):
            self.assertEqual(v.main(), 1)

    def test_live_tree_is_clean(self):
        """Calibration against the real repo — this is the case that goes red
        when someone narrows the sweep's PAGES list for real."""
        proc = subprocess.run(
            [sys.executable, str(GATE)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("superset of both specs", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
