"""Lock the offline-capability implementation gate.

Stdlib-only (mirrors the gate, which runs in the dependency-free CI job). Loads
the script by path so it works without a package install.
"""

from __future__ import annotations

import ast
import importlib.util
import unittest
from pathlib import Path
from unittest import mock

_SCRIPT = (
    Path(__file__).resolve().parents[1] / "verify_offline_capability_implementation.py"
)
_spec = importlib.util.spec_from_file_location("_offline_cap_gate", _SCRIPT)
mod = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(mod)


class AssignedValueTests(unittest.TestCase):
    def test_handles_plain_and_annotated_assign(self):
        tree = ast.parse("X: dict = {'a': 1}\nY = {'b': 2}\n")
        x = y = None
        for node in ast.walk(tree):
            x = x or mod._assigned_value(node, "X")
            y = y or mod._assigned_value(node, "Y")
        self.assertIsInstance(x, ast.Dict)
        self.assertIsInstance(y, ast.Dict)

    def test_iter_set_literals_unwraps_frozenset(self):
        tree = ast.parse("V = frozenset({'a', 'b'})")
        node = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign))
        self.assertEqual(
            {e.value for e in mod._iter_set_literals(node.value)}, {"a", "b"}
        )


class RealTreeTests(unittest.TestCase):
    def test_declared_capabilities_match_taxonomy(self):
        self.assertEqual(
            mod._declared_queued_write_capabilities(),
            {
                "enable_offline_form_queue",
                "enable_offline_attendance_sync",
                "enable_offline_grade_sync",
                "enable_offline_homework_sync",
                "enable_offline_fee_payment_sync",
                "enable_offline_migration_cloud_upload",
            },
        )

    def test_wal_registry_and_allowlist_agree(self):
        registry = mod._wal_string_set(mod.WAL_WRITERS, "_REGISTRY")
        allowed = mod._wal_string_set(mod.WAL_CONSUMERS, "_ALLOWED_DOMAINS")
        self.assertIn("attendance", registry)
        self.assertIn("grade", registry)
        # Producer (registry) and consumer allow-list must list the same domains,
        # else a write is accepted-but-undrained or drained-but-rejected.
        self.assertEqual(registry, allowed)

    def test_real_tree_is_honest(self):
        # Every declared capability has a real producer + applier today.
        self.assertEqual(mod.main([]), 0)


class TheaterDetectionTests(unittest.TestCase):
    def test_declared_capability_without_implementation_fails(self):
        ghost = "enable_offline_ghost_sync"
        ghost_spec = dict(mod._CAPABILITY_SPEC)
        ghost_spec[ghost] = {
            "sodp_tokens": ("ghost.nope",),
            "sodp_members": ("GHOST_NOPE",),
            "wal_domains": (),
            "form_kinds": (),
            "generic": False,
        }
        with mock.patch.object(
            mod,
            "_declared_queued_write_capabilities",
            return_value=set(ghost_spec),
        ), mock.patch.object(mod, "_CAPABILITY_SPEC", ghost_spec):
            self.assertEqual(mod.main([]), 1)

    def test_unmapped_taxonomy_capability_fails(self):
        with mock.patch.object(
            mod,
            "_declared_queued_write_capabilities",
            return_value=set(mod._CAPABILITY_SPEC) | {"enable_offline_unmapped_sync"},
        ):
            self.assertEqual(mod.main([]), 1)


# ---------------------------------------------------------------------------
# MUST-FIRE negative controls for the "gate that cannot fail" defect.
#
# Until 2026-07-21 this gate concatenated every JS file into one blob and ran
# ``re.search`` over it, and matched server members with ``\bNAME\b`` over the
# raw text of offline_queue.py. Both are satisfied by a COMMENT. The tests below
# reintroduce exactly that defect and assert the gate turns red. Each also
# asserts that the naive textual check WOULD have passed, so the test proves the
# gate is doing structural work and is not merely green by accident.
# ---------------------------------------------------------------------------

# Producer mentioned only in a `//` comment and inside an unrelated string.
# One honest producer (attendance) is kept so the failure isolates cleanly.
_COMMENT_ONLY_PRODUCER_JS = """
// TODO(offline): wire the receipt form with
//   action_type: 'payment_receipt'
// nothing below implements it.
var HELP = "pass action_type: 'payment_receipt' to queue a receipt";
window.rmcOfflineEnqueue({ action_type: 'attendance', payload: {} });
"""

# Server member named only in a docstring and a `#` comment.
_COMMENT_ONLY_SERVER_QUEUE = '''
def _apply_payload(action, *, force_local=False):
    """Dispatch. Handles PAYMENT_RECEIPT and PAYMENT_PROOF."""
    # PAYMENT_RECEIPT / PAYMENT_PROOF: not implemented yet.
    if at == OfflineAction.ActionType.ATTENDANCE:
        return _apply_attendance(sid, uid, payload)
    return {"ok": False, "error": "unknown"}
'''


class CommentOnlyMustFireTests(unittest.TestCase):
    """Reintroduce the defect; the gate must go red."""

    def _patched_read(self, queue_src):
        real_read = mod._read

        def _read(path):
            return queue_src if path == mod.OFFLINE_QUEUE else real_read(path)

        return _read

    def test_producer_only_in_a_comment_is_not_a_producer(self):
        # The old textual check would have matched this happily.
        self.assertRegex(_COMMENT_ONLY_PRODUCER_JS, r"action_type\s*:\s*'payment_receipt'")
        with mock.patch.object(
            mod, "_js_sources", return_value=[_COMMENT_ONLY_PRODUCER_JS]
        ):
            facts = mod._client_producer_facts()
            self.assertNotIn("payment_receipt", facts["action_types"])
            # The honest sibling in the same blob still resolves.
            self.assertIn("attendance", facts["action_types"])
            report = mod.main(["--json"])
        self.assertEqual(report, 1)

    def test_server_member_only_in_a_comment_is_not_an_applier(self):
        # The old textual check would have matched this happily.
        self.assertRegex(_COMMENT_ONLY_SERVER_QUEUE, r"\bPAYMENT_RECEIPT\b")
        self.assertRegex(_COMMENT_ONLY_SERVER_QUEUE, r"\bPAYMENT_PROOF\b")
        dispatched = mod._dispatched_members(
            _COMMENT_ONLY_SERVER_QUEUE, mod._enum_member_names()
        )
        self.assertNotIn("PAYMENT_RECEIPT", dispatched)
        self.assertNotIn("PAYMENT_PROOF", dispatched)
        self.assertIn("ATTENDANCE", dispatched)  # the real branch still counts

    def test_whole_gate_red_when_capability_exists_only_as_prose(self):
        with mock.patch.object(
            mod, "_js_sources", return_value=[_COMMENT_ONLY_PRODUCER_JS]
        ), mock.patch.object(
            mod, "_read", side_effect=self._patched_read(_COMMENT_ONLY_SERVER_QUEUE)
        ):
            self.assertEqual(mod.main([]), 1)

    def test_dead_branch_is_not_a_dispatch(self):
        """A branch that names the member but does no work must not count."""
        src = (
            "def _apply_payload(action):\n"
            "    if at == OfflineActionType.PAYMENT_PROOF:\n"
            "        pass\n"
            "    return {'ok': False}\n"
        )
        self.assertNotIn(
            "PAYMENT_PROOF", mod._dispatched_members(src, mod._enum_member_names())
        )

    def test_ui_surface_in_an_html_comment_does_not_count(self):
        stripped = mod._strip_markup_comments(
            '<!-- <form data-rmc-offline-form="payment_receipt"> -->'
        )
        self.assertNotIn("payment_receipt", stripped)


class JsTokeniserTests(unittest.TestCase):
    def test_comments_dropped_and_strings_atomic(self):
        toks = mod._js_tokenize("// x('a')\nvar s = \"y('b')\";\nf('c');")
        values = [t.value for t in toks if t.kind in mod._STRING_KINDS]
        self.assertEqual(values, ['"y(\'b\')"', "'c'"])

    def test_enqueue_call_site_resolves_nested_object_literal(self):
        toks = mod._js_tokenize(
            "window.rmcOfflineEnqueue({ payload: { note: 'x' }, "
            "action_type: 'grading' });"
        )
        self.assertEqual(mod._enqueued_action_types(toks), {"grading"})

    def test_wal_domain_identifier_resolved_from_enclosing_block(self):
        toks = mod._js_tokenize(
            "function wire() {\n"
            "  let domain;\n"
            "  if (x) { domain = 'attendance'; } else { domain = 'teacher_attendance'; }\n"
            "  window.rmcWAL.append(domain, actions);\n"
            "}\n"
        )
        self.assertEqual(
            mod._wal_appended_domains(toks), {"attendance", "teacher_attendance"}
        )

    def test_wal_domain_in_a_comment_is_not_appended(self):
        toks = mod._js_tokenize("// window.rmcWAL.append('billing_charge', a);\n")
        self.assertEqual(mod._wal_appended_domains(toks), set())


if __name__ == "__main__":
    unittest.main()
