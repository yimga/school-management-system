"""Unit tests for scripts/scan_granular_rbac_adoption.py (stdlib, no Django).

Locks the coarse-gate classification core so the RBAC-adoption ratchet cannot silently rot:
tenant_admin_required detection (bare + called + method_decorator), the
permission_required("settings.*") special case, granular/operator exemptions, and the
allow-marker suppression.
"""
import ast
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import scan_granular_rbac_adoption as m  # noqa: E402


def _dec(src: str):
    """Return the first decorator node of a decorated def/class in `src`."""
    node = ast.parse(src).body[0]
    return node.decorator_list[0]


class CoarseDetectionTest(unittest.TestCase):
    def test_bare_tenant_admin_required(self):
        self.assertEqual(
            m._decorator_is_coarse(_dec("@tenant_admin_required\ndef v(r): pass")),
            "tenant_admin_required",
        )

    def test_called_tenant_admin_required(self):
        self.assertEqual(
            m._decorator_is_coarse(_dec("@tenant_admin_required(codes=('x',))\ndef v(r): pass")),
            "tenant_admin_required",
        )

    def test_method_decorator_tenant_admin(self):
        self.assertEqual(
            m._decorator_is_coarse(
                _dec('@method_decorator(tenant_admin_required, name="dispatch")\nclass V: pass')
            ),
            "tenant_admin_required",
        )

    def test_permission_required_settings_manage(self):
        self.assertEqual(
            m._decorator_is_coarse(_dec('@permission_required("settings.manage")\ndef v(r): pass')),
            "permission_required:settings",
        )

    def test_permission_required_feature_control(self):
        self.assertEqual(
            m._decorator_is_coarse(_dec('@permission_required("settings.feature_control")\ndef v(r): pass')),
            "permission_required:settings",
        )

    def test_permission_required_granular_not_coarse(self):
        # A granular code is NOT a coarse gate — it must not be counted.
        self.assertIsNone(
            m._decorator_is_coarse(_dec('@permission_required("finance.manage")\ndef v(r): pass'))
        )

    def test_require_permission_not_coarse(self):
        self.assertIsNone(
            m._decorator_is_coarse(_dec('@require_permission("finance.view", "finance.manage")\ndef v(r): pass'))
        )

    def test_login_required_not_coarse(self):
        self.assertIsNone(m._decorator_is_coarse(_dec("@login_required\ndef v(r): pass")))


class ScanTreeTest(unittest.TestCase):
    def _scan_over(self, files: dict):
        with tempfile.TemporaryDirectory() as tmp:
            app_rel = "apps/finance"
            for name, content in files.items():
                p = os.path.join(tmp, app_rel.replace("/", os.sep), name)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(content)
            orig_root, orig_dirs = m.REPO_ROOT, m._OPERATIONAL_APP_DIRS
            m.REPO_ROOT, m._OPERATIONAL_APP_DIRS = tmp, (app_rel,)
            try:
                return m.scan()
            finally:
                m.REPO_ROOT, m._OPERATIONAL_APP_DIRS = orig_root, orig_dirs

    def test_flags_unmarked_coarse_gate(self):
        findings = self._scan_over(
            {"views_x.py": "@tenant_admin_required\ndef dash(request): pass\n"}
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["view"], "dash")
        self.assertEqual(findings[0]["kind"], "tenant_admin_required")

    def test_marker_suppresses(self):
        findings = self._scan_over(
            {
                "views_x.py": "# rbac-coarse-allow: intentional admin-only console\n"
                "@tenant_admin_required\ndef dash(request): pass\n"
            }
        )
        self.assertEqual(findings, [])

    def test_granular_not_flagged(self):
        findings = self._scan_over(
            {"views_x.py": '@require_permission("finance.manage")\ndef mut(request): pass\n'}
        )
        self.assertEqual(findings, [])

    def test_skips_tests_and_migrations(self):
        findings = self._scan_over(
            {
                "tests/test_x.py": "@tenant_admin_required\ndef t(request): pass\n",
                "migrations/0001_x.py": "@tenant_admin_required\ndef mgr(request): pass\n",
            }
        )
        self.assertEqual(findings, [])


class LiveTreeBaselineTest(unittest.TestCase):
    """The live repo tree must not exceed its recorded baseline (belt-and-suspenders)."""

    def test_repo_within_baseline(self):
        baseline = m._load_baseline()
        cur = m._multiset(m.scan())
        new = cur - m._multiset(baseline.get("findings", []))
        self.assertEqual(sum(new.values()), 0, f"new coarse operational gates: {dict(new)}")


if __name__ == "__main__":
    unittest.main()
