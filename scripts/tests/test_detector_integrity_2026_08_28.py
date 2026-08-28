"""Tests for the two detector-integrity tools added 2026-08-28.

``verify_gates_can_fail`` is itself a gate, so the thing worth asserting is the
property that makes it useful: EVERY gate the pre-push runner enforces is either
proven by a mutation or carries a reasoned exemption. That assertion goes red
the moment somebody adds a gate and forgets its proof, which is exactly when it
should.

``audit_worktree_health`` deletes directories, so the thing worth asserting is
that it refuses to when it cannot answer the safety question.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import audit_worktree_health as awh  # noqa: E402
import verify_gates_can_fail as vgcf  # noqa: E402


class GateProofCoverageTests(unittest.TestCase):
    def test_every_registered_gate_is_proven_or_reasoned(self):
        problems = vgcf.completeness_problems()
        self.assertEqual(
            problems,
            [],
            "a pre-push gate has no mutation and no reasoned exemption:\n  "
            + "\n  ".join(problems),
        )

    def test_registry_covers_both_gate_lists(self):
        labels = {label for label, _, _ in vgcf.registered_gates()}
        self.assertGreater(len(labels), 50)
        # Both halves of pre_push_boundary_check must be represented, or the
        # harness would silently prove only the deps-free ones.
        self.assertIn("python-files-parse", labels)
        self.assertIn("single-migration-leaf", labels)

    def test_exemptions_carry_a_real_reason(self):
        for label, reason in vgcf.UNPROVEN.items():
            self.assertGreater(
                len(reason), 40, f"{label}: an exemption needs a reason, not a placeholder"
            )

    def test_crlf_variants_cover_the_line_endings_in_this_repo(self):
        variants = vgcf._crlf_variants(b"a\nb")
        self.assertIn(b"a\nb", variants)
        self.assertIn(b"a\r\nb", variants)
        # Some files here are committed with \r\r\n; an anchor that only tries
        # LF reports SKIP on those, which reads as "nothing to prove".
        self.assertIn(b"a\r\r\nb", variants)


class MutationRoundTripTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.workspace = vgcf.Workspace(self.tmp)
        self.workspace.path = self.tmp

    def tearDown(self):
        import shutil

        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_then_restore_leaves_no_trace(self):
        mutation = vgcf.Mutation(kind="create", path="new.py", defect="x", content=b"boom\n")
        applied, why, token = self.workspace.apply(mutation)
        self.assertTrue(applied, why)
        self.assertTrue((self.tmp / "new.py").exists())
        self.workspace.restore(mutation, token)
        self.assertFalse((self.tmp / "new.py").exists())

    def test_patch_restores_the_original_bytes_including_crlf(self):
        target = self.tmp / "crlf.py"
        original = b"line one\r\nFORCE ROW LEVEL SECURITY\r\nline three\r\n"
        target.write_bytes(original)
        mutation = vgcf.Mutation(
            kind="patch",
            path="crlf.py",
            defect="x",
            anchor=b"FORCE ROW LEVEL SECURITY",
            replacement=b"ROW LEVEL SECURITY",
        )
        applied, why, token = self.workspace.apply(mutation)
        self.assertTrue(applied, why)
        self.assertNotIn(b"FORCE", target.read_bytes())
        self.workspace.restore(mutation, token)
        self.assertEqual(target.read_bytes(), original)

    def test_a_drifted_anchor_is_reported_not_silently_skipped(self):
        (self.tmp / "f.py").write_bytes(b"nothing to see\n")
        mutation = vgcf.Mutation(
            kind="patch", path="f.py", defect="x", anchor=b"gone", replacement=b"x"
        )
        applied, why, _ = self.workspace.apply(mutation)
        self.assertFalse(applied)
        self.assertIn("drifted", why)


class WorktreeSafetyTests(unittest.TestCase):
    def test_unresolvable_ref_is_unknown_not_safe(self):
        worktree = awh.Worktree(
            path=pathlib.Path("C:/definitely/not/here")
            if sys.platform == "win32"
            else pathlib.Path("/definitely/not/here"),
            head="deadbeef1",
            branch="no/such/branch-for-tests",
            locked=False,
        )
        awh.classify(worktree, ROOT)
        self.assertEqual(worktree.state, "GONE")
        self.assertEqual(worktree.unmerged, -1, "an unanswerable safety check must not read as 0")
        self.assertFalse(worktree.removable)

    def test_the_main_checkout_is_never_a_removal_candidate(self):
        worktree = awh.Worktree(path=ROOT, head="", branch="main", locked=False)
        awh.classify(worktree, ROOT)
        self.assertEqual(worktree.state, "LIVE")
        self.assertFalse(worktree.removable)

    def test_a_checkout_missing_its_markers_is_hollow(self):
        import tempfile

        tmp = pathlib.Path(tempfile.mkdtemp())
        try:
            worktree = awh.Worktree(path=tmp, head="deadbeef1", branch="main", locked=False)
            awh.classify(worktree, ROOT)
            self.assertEqual(worktree.state, "HOLLOW")
        finally:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
