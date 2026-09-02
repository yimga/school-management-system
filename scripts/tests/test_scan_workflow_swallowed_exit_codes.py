"""Tests for scan_workflow_swallowed_exit_codes.

The gate's correct answer is zero, so these tests exist to prove the detector
can say something other than zero -- and to pin the shapes it must NOT flag,
because a gate that cries wolf on a cleanup line or a readiness poll is a gate
somebody switches off, and then the real ones ride back in behind it.
"""
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "scan_workflow_swallowed_exit_codes",
    REPO / "scripts" / "scan_workflow_swallowed_exit_codes.py",
)
gate = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(gate)


def wf(body: str) -> str:
    return "jobs:\n  a:\n    steps:\n" + body


class SelfCheckTests(unittest.TestCase):
    def test_bundled_self_check_passes(self):
        self.assertTrue(gate.self_check())


class FindingTests(unittest.TestCase):
    def test_or_true_on_last_line_of_block(self):
        hits = gate.analyse(wf("      - run: |\n          pytest tests/ || true\n"))
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][1], "swallow-on-last-command")

    def test_or_echo_on_last_line_of_block(self):
        hits = gate.analyse(
            wf('      - run: |\n          npx playwright test x.js || echo "skipped"\n')
        )
        self.assertEqual(len(hits), 1)

    def test_or_colon_on_last_line(self):
        hits = gate.analyse(wf("      - run: |\n          pytest tests/ || :\n"))
        self.assertEqual(len(hits), 1)

    def test_or_exit_zero_on_last_line(self):
        hits = gate.analyse(wf("      - run: |\n          pytest tests/ || exit 0\n"))
        self.assertEqual(len(hits), 1)

    def test_inline_run_scalar(self):
        hits = gate.analyse(wf("      - run: chromedriver --version || true\n"))
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][1], "swallow-on-inline-run")

    def test_trailing_comment_does_not_hide_the_swallow(self):
        hits = gate.analyse(
            wf("      - run: |\n          pytest tests/ || true\n          # done\n\n")
        )
        self.assertEqual(len(hits), 1)

    def test_folded_continuation_is_still_the_last_command(self):
        hits = gate.analyse(
            wf(
                "      - run: |\n"
                "          pip-audit --requirement requirements.txt \\\n"
                "            --strict || true\n"
            )
        )
        self.assertEqual(len(hits), 1)

    def test_continue_on_error_true(self):
        hits = gate.analyse(wf("      - run: pytest\n        continue-on-error: true\n"))
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0][1], "continue-on-error")

    def test_continue_on_error_expression_is_reported(self):
        # A templated value can evaluate to true; a human must look at it.
        hits = gate.analyse(
            wf("      - run: pytest\n        continue-on-error: ${{ vars.SOFT }}\n")
        )
        self.assertEqual(len(hits), 1)


class NonFindingTests(unittest.TestCase):
    def test_swallow_before_a_real_command_is_not_a_finding(self):
        self.assertEqual(
            gate.analyse(
                wf("      - run: |\n          ls -la dist/ || true\n          test -f dist/a.zip\n")
            ),
            [],
        )

    def test_cleanup_swallow_before_exit_1(self):
        self.assertEqual(
            gate.analyse(
                wf(
                    "      - run: |\n"
                    '          kill "$(cat /tmp/x.pid)" 2>/dev/null || true\n'
                    "          exit 1\n"
                )
            ),
            [],
        )

    def test_readiness_poll_sentinel(self):
        self.assertEqual(
            gate.analyse(
                wf(
                    "      - run: |\n          for i in 1 2 3; do\n"
                    "            code=$(curl -s http://x/ || echo \"000\")\n"
                    '            [ "$code" = 200 ] && break\n          done\n'
                    "          npx playwright test spec.js\n"
                )
            ),
            [],
        )

    def test_tiered_gate_ending_in_fi(self):
        self.assertEqual(
            gate.analyse(
                wf(
                    '      - run: |\n          if [ "$STRICT" = 1 ]; then\n'
                    "            lhci autorun\n          else\n"
                    '            lhci autorun || echo "::warning::below budget"\n'
                    "          fi\n"
                )
            ),
            [],
        )

    def test_enforcing_brace_fallback(self):
        self.assertEqual(
            gate.analyse(
                wf(
                    "      - run: |\n"
                    '          bandit -r apps || { echo "::error::HIGH"; exit 1; }\n'
                )
            ),
            [],
        )

    def test_command_fallback_is_out_of_scope_by_design(self):
        # `npm ci || npm install` hides the first command's failure, but the
        # shape is sometimes a correct idempotent idiom (see tenants-rls.yml's
        # CREATE ROLE). Telling them apart would need an allowlist, which is
        # what this class of defect hides behind.
        self.assertEqual(
            gate.analyse(wf("      - run: npm ci || npm install --no-audit --no-fund\n")),
            [],
        )

    def test_continue_on_error_false(self):
        self.assertEqual(
            gate.analyse(wf("      - run: pytest\n        continue-on-error: false\n")), []
        )

    def test_clean_step(self):
        self.assertEqual(gate.analyse(wf("      - run: |\n          pytest tests/\n")), [])


class LiveTreeTests(unittest.TestCase):
    def test_every_tracked_workflow_is_clean(self):
        findings = []
        for rel in gate.tracked_workflows():
            text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
            for line_no, kind, evidence in gate.analyse(text):
                findings.append(f"{rel}:{line_no} [{kind}] {evidence}")
        self.assertEqual(findings, [], "\n".join(findings))

    def test_the_corpus_is_not_empty(self):
        # A zero over an empty corpus is not a zero. `git ls-files` returning
        # nothing would make every other assertion here vacuously true.
        self.assertGreater(len(gate.tracked_workflows()), 50)


if __name__ == "__main__":
    unittest.main()
