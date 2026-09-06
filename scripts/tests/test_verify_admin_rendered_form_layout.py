"""Tests for the admin rendered-form browser proof.

The browser-dependent half is proven by the gate's own ``--self-check``, which
runs the real assertions against known-bad pages and is wired into
``verify_gates_can_fail``. What is pinned here is everything that can be wrong
without a browser -- and one regression that cost a whole run.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import pathlib
import re
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "verify_admin_rendered_form_layout.py"

_spec = importlib.util.spec_from_file_location("_rmc_admin_layout_gate", MODULE_PATH)
gate = importlib.util.module_from_spec(_spec)
sys.modules["_rmc_admin_layout_gate"] = gate
_spec.loader.exec_module(gate)


class SkipContractTests(unittest.TestCase):
    def test_skip_exit_code_is_two(self):
        """pre_push_boundary_check renders 2 as SKIP. A gate that cannot run
        has not passed, so this must never become 0."""
        self.assertEqual(gate._SKIPPED_EXIT_CODE, 2)

    def test_widths_must_include_one_below_the_lg_breakpoint(self):
        """The stacked-label layout only exists below lg. A run that never goes
        there cannot see the doubled header, so it must refuse rather than
        report a comfortable zero."""
        argv = sys.argv
        try:
            sys.argv = ["gate", "--widths", "1440,1600"]
            self.assertEqual(gate.main(), 1)
        finally:
            sys.argv = argv


class DeadlineTests(unittest.TestCase):
    """Being killed by the runner is the one outcome this gate must not have.

    pre_push_boundary_check reports a kill as FAIL, which its own comment calls
    indistinguishable from a real finding. A full pass measured 225s; the
    ceiling is 600s. The gate's own deadline has to stay under it.
    """

    def test_the_deadline_is_under_the_pre_push_ceiling(self):
        runner = (ROOT / "scripts" / "pre_push_boundary_check.py").read_text(
            encoding="utf-8")
        match = re.search(
            r"RMC_PREPUSH_GATE_TIMEOUT_S[\"\']\)\s*or\s*(\d+)", runner)
        self.assertIsNotNone(match, "could not read the runner's ceiling")
        self.assertLess(gate._DEADLINE_S, int(match.group(1)))

    def test_the_deadline_leaves_room_to_actually_measure(self):
        self.assertGreater(gate._DEADLINE_S, gate._MIN_BROWSER_S * 2)


class BrowserDiscoveryTests(unittest.TestCase):
    def test_env_override_that_does_not_exist_is_not_accepted(self):
        import os

        previous = os.environ.get("RMC_HEADLESS_BROWSER")
        try:
            os.environ["RMC_HEADLESS_BROWSER"] = str(ROOT / "no-such-browser")
            self.assertIsNone(gate.find_browser())
        finally:
            if previous is None:
                os.environ.pop("RMC_HEADLESS_BROWSER", None)
            else:
                os.environ["RMC_HEADLESS_BROWSER"] = previous

    def test_env_override_is_used_when_it_exists(self):
        import os

        previous = os.environ.get("RMC_HEADLESS_BROWSER")
        try:
            os.environ["RMC_HEADLESS_BROWSER"] = str(MODULE_PATH)
            self.assertEqual(gate.find_browser(), str(MODULE_PATH))
        finally:
            if previous is None:
                os.environ.pop("RMC_HEADLESS_BROWSER", None)
            else:
                os.environ["RMC_HEADLESS_BROWSER"] = previous


class DriverTests(unittest.TestCase):
    def _driver(self, pages=("alpha", "beta"), widths=(1440, 900), budget=25000):
        return gate._DRIVER % {
            "measure": gate.MEASURE_JS,
            "pages": json.dumps(sorted(pages)),
            "widths": json.dumps(list(widths)),
            "budget": budget,
        }

    def test_driver_embeds_the_shared_assertions(self):
        """One copy of the assertions, so --self-check proves what runs."""
        self.assertIn(gate.MEASURE_JS, self._driver())

    def test_driver_carries_pages_widths_and_budget(self):
        html = self._driver()
        self.assertIn('"alpha"', html)
        self.assertIn("1440", html)
        self.assertIn("900", html)
        self.assertIn("25000", html)

    def test_driver_carries_the_row_count_back(self):
        """The count is what separates a clean run from a run that never
        reached the assertion. Without it this gate reported "every inline row
        paints" while measuring 2 rows across 60 inline groups."""
        html = self._driver()
        self.assertIn("measured.rows", html)
        self.assertIn("rows: measured.rows", html)

    def test_driver_waits_for_load_and_two_frames_not_a_sleep(self):
        """A sleep loses the race: at 0.6s this page is still `loading` with 84
        of 93 stylesheets attached and every element at zero client rects, which
        reads as a finding on a healthy page."""
        html = self._driver()
        self.assertIn("frame.onload", html)
        self.assertEqual(html.count("requestAnimationFrame"), 2)
        self.assertNotIn("setTimeout(() => resolve", html)


class ReachTests(unittest.TestCase):
    """The gate must reach the branch that emits its central finding.

    Its first cut did not. 31 of this repo's tabular inlines declare
    ``extra = 0`` against 2 that declare ``extra = 1``, so an admin ADD page
    renders the __prefix__ prototype and no row a user can type into. The
    defect re-planted verbatim exited 0.
    """

    SOURCE = MODULE_PATH.read_text(encoding="utf-8")

    def test_rendering_forces_an_offered_row(self):
        self.assertIn("TabularInline.get_extra = _at_least_one_row", self.SOURCE)
        self.assertIn("max(1, original_get_extra(", self.SOURCE)

    def test_the_forcing_is_undone_in_a_finally(self):
        """It patches a Django base class. A run that raises must not leave
        every tabular inline in the process holding a forced extra."""
        body = self.SOURCE.split("TabularInline.get_extra = _at_least_one_row")[1]
        finally_block = body.split("finally:")[1][:400]
        self.assertIn("TabularInline.get_extra = original_get_extra", finally_block)
        self.assertIn("del TabularInline.get_extra", finally_block)

    def test_the_prototype_is_identified_by_id_AND_class(self):
        """Unfold names the prototype by id and shares its class with every
        new row. Keying on the id alone silently skips a real row whose id
        happens to end in -empty, and a skipped row can never be reported."""
        self.assertIn("classList.contains('empty-form')", gate.MEASURE_JS)


class VacuityGuardTests(unittest.TestCase):
    """A zero from a detector that measured nothing is not a pass."""

    def _run_main(self, rows):
        saved = (gate.find_browser, gate.self_check, gate.discover_and_render,
                 gate._run_browser, sys.argv)
        try:
            gate.find_browser = lambda: "a-browser"
            gate.self_check = lambda verbose=True: True
            gate.discover_and_render = lambda tmpdir: ({"alpha": b"x"}, [])
            gate._run_browser = lambda pages, widths, **kw: (
                [{"page": "alpha", "width": w, "findings": [], "rows": rows}
                 for w in widths], None)
            sys.argv = ["gate"]
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = gate.main()
            return code, buffer.getvalue()
        finally:
            (gate.find_browser, gate.self_check, gate.discover_and_render,
             gate._run_browser, sys.argv) = saved

    def test_no_rows_measured_refuses_to_report(self):
        code, out = self._run_main(0)
        self.assertEqual(code, 1)
        self.assertIn("REFUSING TO REPORT", out)

    def test_rows_measured_and_no_findings_is_a_pass(self):
        code, out = self._run_main(3)
        self.assertEqual(code, 0)
        self.assertIn("offered rows", out)


class SelfCheckCaseTests(unittest.TestCase):
    def test_every_case_has_the_structures_the_assertions_key_on(self):
        for name, (html, _expected) in gate.SELF_CHECK_CASES.items():
            with self.subTest(case=name):
                self.assertIn("inline-group", html)
                self.assertIn("<tbody>", html)
                self.assertIn('id="g-empty"', html)
                self.assertIn("empty-form", html)

    def test_there_is_a_bad_case_for_every_finding_kind(self):
        """A detector never shown finding a thing is not evidence it would."""
        expected = set()
        for _html, kinds in gate.SELF_CHECK_CASES.values():
            expected |= kinds
        self.assertEqual(
            expected,
            {"inline-row-not-painted", "prototype-row-painted", "header-layers"},
        )

    def test_a_real_row_named_like_the_prototype_is_covered(self):
        """The shadowing trap: a real row whose id ends in -empty. A check
        keyed on the name alone treats it as the phantom and reports nothing
        at all."""
        html, expected = gate.SELF_CHECK_CASES["real_row_named_empty"]
        self.assertIn('id="g-0-empty"', html)
        self.assertNotIn('id="g-0-empty" class="empty-form"', html)
        self.assertEqual(expected, {"inline-row-not-painted"})

    def test_a_row_can_be_hidden_at_the_tbody_or_at_the_tr(self):
        """Both mechanisms must be covered. The first cut of this gate only
        checked the tbody and silently missed the tr case."""
        self.assertIn("hidden_row_tbody", gate.SELF_CHECK_CASES)
        self.assertIn("hidden_row_tr", gate.SELF_CHECK_CASES)


class ReportEndpointTests(unittest.TestCase):
    """Regression: only the driver may report.

    These are real admin pages and they carry the platform's own click-ingest
    beacon, which POSTs {"page_path": ...} to a relative URL. Accepting a POST
    on any path let that telemetry overwrite the run's results -- the whole run
    ended holding a dict where fifty measurements belonged.
    """

    def setUp(self):
        gate._Handler.pages = {"alpha": b"<!doctype html>alpha"}
        gate._Handler.report = {}
        gate._Handler.done = threading.Event()
        gate._Handler.driver_html = b"<!doctype html>driver"
        gate._Handler.serve_static = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), gate._Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()

    def _post(self, path, payload):
        request = urllib.request.Request(
            "http://127.0.0.1:%d%s" % (self.port, path),
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status

    def test_a_beacon_post_does_not_become_the_report(self):
        self._post("/click-ingest", {"page_path": "/p/alpha"})
        # wait(), not is_set(): do_POST answers the request BEFORE it touches
        # the event, so the client returns first and is_set() races it.
        self.assertFalse(gate._Handler.done.wait(timeout=0.5))
        self.assertNotIn("data", gate._Handler.report)

    def test_the_driver_report_is_accepted(self):
        payload = [{"page": "alpha", "width": 1440, "findings": []}]
        self._post("/report", payload)
        self.assertTrue(gate._Handler.done.wait(timeout=5))
        self.assertEqual(gate._Handler.report.get("data"), payload)

    def test_pages_are_served_and_unknown_paths_404(self):
        with urllib.request.urlopen(
            "http://127.0.0.1:%d/p/alpha" % self.port, timeout=5
        ) as response:
            self.assertEqual(response.read(), b"<!doctype html>alpha")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(
                "http://127.0.0.1:%d/p/nope" % self.port, timeout=5
            )
        self.assertEqual(caught.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
