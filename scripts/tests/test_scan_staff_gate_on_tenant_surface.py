"""Unit tests for scripts/scan_staff_gate_on_tenant_surface.py (stdlib, no Django).

Locks the scanner's classification core so the H1 seal cannot silently rot:
staff_member_required detection, control-plane exemption, method_decorator
unwrapping, f-string path patterns, and the super-segment skip.
"""
import ast
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import scan_staff_gate_on_tenant_surface as m  # noqa: E402


def _def(src: str):
    return ast.parse(src).body[0]


def _call(src: str) -> ast.Call:
    return ast.parse(src, mode="eval").body


class SuperSegmentTest(unittest.TestCase):
    def test_super_prefix_and_segment(self):
        self.assertTrue(m._has_super_segment("/super/dashboard/"))
        self.assertTrue(m._has_super_segment("portal/super/merges/"))
        self.assertTrue(m._has_super_segment("api/v1/super/pulse"))

    def test_non_super(self):
        self.assertFalse(m._has_super_segment("portal/parent/"))
        self.assertFalse(m._has_super_segment("supervisor/"))  # substring, not a segment
        self.assertFalse(m._has_super_segment(""))


class PathLiteralTest(unittest.TestCase):
    def test_plain_string(self):
        self.assertEqual(m._path_literal(_call('path("super/merges/", v)')), "super/merges/")

    def test_fstring_keeps_super_segment(self):
        got = m._path_literal(_call('path(f"super/wizards/{key}/", v)'))
        self.assertIn("super", got.strip("/").split("/"))

    def test_non_literal(self):
        self.assertEqual(m._path_literal(_call("path(SOME_VAR, v)")), "")


class DecoratorTokenTest(unittest.TestCase):
    def test_staff_member_required_detected(self):
        toks = m._view_decorator_tokens(_def("@staff_member_required\n@require_safe\ndef v(): pass"))
        self.assertIn(m.STAFF_TOKEN, toks)

    def test_control_plane_detected(self):
        toks = m._view_decorator_tokens(_def("@require_control_plane_access\ndef v(): pass"))
        self.assertTrue(toks & m.CONTROL_PLANE_TOKENS)

    def test_method_decorator_unwrapped(self):
        toks = m._view_decorator_tokens(
            _def('@method_decorator(staff_member_required, name="dispatch")\nclass V: pass')
        )
        self.assertIn(m.STAFF_TOKEN, toks)

    def test_method_decorator_control_plane_unwrapped(self):
        toks = m._view_decorator_tokens(
            _def('@method_decorator(require_control_plane_access, name="dispatch")\nclass V: pass')
        )
        self.assertTrue(toks & m.CONTROL_PLANE_TOKENS)

    def test_dispatch_method_decorators_seen(self):
        src = (
            "class V:\n"
            "    @staff_member_required\n"
            "    def dispatch(self, r): pass\n"
        )
        self.assertIn(m.STAFF_TOKEN, m._view_decorator_tokens(_def(src)))


class LiveTreeInvariantTest(unittest.TestCase):
    """The live repo tree must stay at baseline 0 (belt-and-suspenders with CI)."""

    def test_repo_tree_clean(self):
        root = m._module_to_file(m.TENANT_ROOT_MODULE)
        self.assertIsNotNone(root, "config/tenant_urls.py must resolve")
        findings = m.scan(root)
        self.assertEqual(
            findings, [], f"unexpected staff-gate-on-tenant-surface findings: {findings}"
        )


class TenantOnlyAppSweepTest(unittest.TestCase):
    """The belt-and-suspenders sweep catches a staff gate the route resolver misses
    (e.g. a view re-exported through a package __init__ — how the finance dashboard's
    gate went undetected)."""

    def _run_sweep_over(self, files: dict):
        with tempfile.TemporaryDirectory() as tmp:
            app_rel = "apps/fake_tenant"
            for name, content in files.items():
                p = os.path.join(tmp, app_rel.replace("/", os.sep), name)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(content)
            orig_root, orig_dirs = m.REPO_ROOT, m._TENANT_ONLY_APP_DIRS
            m.REPO_ROOT, m._TENANT_ONLY_APP_DIRS = tmp, (app_rel,)
            m._parse.cache_clear()
            m._raw_lines.cache_clear()
            try:
                return m._scan_tenant_only_app_modules()
            finally:
                m.REPO_ROOT, m._TENANT_ONLY_APP_DIRS = orig_root, orig_dirs
                m._parse.cache_clear()
                m._raw_lines.cache_clear()

    def test_sweep_flags_unmarked_staff_gate(self):
        findings = self._run_sweep_over(
            {"views_dashboard.py": "@staff_member_required\ndef dashboard(request): pass\n"}
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["view"], "dashboard")

    def test_sweep_clears_marked(self):
        findings = self._run_sweep_over(
            {
                "views_dashboard.py": "# tenant-surface-staff-allow: reviewed\n"
                "@staff_member_required\ndef dashboard(request): pass\n"
            }
        )
        self.assertEqual(findings, [])

    def test_sweep_clears_control_plane(self):
        findings = self._run_sweep_over(
            {
                "views_ops.py": "@require_control_plane_access\n"
                "@staff_member_required\ndef ops(request): pass\n"
            }
        )
        self.assertEqual(findings, [])

    def test_sweep_ignores_non_staff(self):
        findings = self._run_sweep_over(
            {"views_plain.py": "@login_required\ndef v(request): pass\n"}
        )
        self.assertEqual(findings, [])

    def test_sweep_skips_tests_and_migrations(self):
        findings = self._run_sweep_over(
            {
                "tests/test_x.py": "@staff_member_required\ndef t(request): pass\n",
                "migrations/0001_x.py": "@staff_member_required\ndef mgr(request): pass\n",
            }
        )
        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
