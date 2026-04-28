"""1051-1053: admin gravity + security surface audits produce loadable JSON artifacts."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent.parent.parent


class AuditScripts1051_1053Tests(unittest.TestCase):
    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(REPO / "scripts" / args[0])] + list(args[1:]),
            cwd=str(REPO),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_audit_admin_gravity_writes_json(self) -> None:
        cp = self._run("audit_admin_gravity.py", "--strict")
        self.assertEqual(cp.returncode, 0, msg=cp.stderr + cp.stdout)
        p = REPO / "docs" / "generated" / "admin_gravity_audit.json"
        self.assertTrue(p.is_file(), msg="admin JSON missing")
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data.get("schema_version"), 1)
        self.assertIn("registrations_by_app", data)
        self.assertIn("control_plane_replacement_candidates", data)
        self.assertIn("control_plane_replacement_roadmap", data)
        self.assertIsInstance(data["control_plane_replacement_roadmap"], list)
        self.assertGreaterEqual(len(data["control_plane_replacement_roadmap"]), 1)
        self.assertIn("product_admin_metadata_namespace_bridge_hits", data)
        self.assertIn("metadata_admin_bridge_hits_by_policy", data)
        self.assertIn("product_admin_stragglers_by_area", data)
        self.assertIn("product_admin_bridge_hits_v2", data)
        self.assertIn("product_admin_bridge_1100_app_trees", data)
        trees = data["product_admin_bridge_1100_app_trees"]
        self.assertIn("apps/studio_os", trees)
        self.assertIn("apps/marketplace", trees)
        self.assertIn("apps/automation", trees)
        summary = data.get("summary") or {}
        self.assertIn("shipped_category_regression_checks", summary)
        reg = summary.get("shipped_category_regression_checks") or {}
        self.assertIn("backend_teacher_cp_before_admin", reg)
        self.assertIn("backend_student_portal_tabbed_before_admin", reg)
        self.assertIn("backend_classroom_academic_years_before_admin", reg)
        self.assertIn(
            "metadata_dynamicfield_admin_bridge_hits", data
        )
        cpath = REPO / "docs" / "generated" / "admin_control_plane_replacement_candidates.json"
        self.assertTrue(cpath.is_file(), msg="admin_control_plane_replacement_candidates.json missing")
        cmap = json.loads(cpath.read_text(encoding="utf-8"))
        self.assertIn("control_plane_replacement_roadmap", cmap)

    def test_audit_security_surface_writes_json(self) -> None:
        cp = self._run("audit_security_surface.py")
        self.assertEqual(cp.returncode, 0, msg=cp.stderr + cp.stdout)
        p = REPO / "docs" / "generated" / "security_surface_audit.json"
        self.assertTrue(p.is_file(), msg="security JSON missing")
        data = json.loads(p.read_text(encoding="utf-8"))
        self.assertEqual(data.get("schema_version"), 1)
        self.assertIn("unified", data)
        self.assertIsInstance(data["unified"], list)
        self.assertIn("summary_by_governance_tier", data)
        if data["unified"]:
            self.assertIn("governance_tier", data["unified"][0])

    def test_verify_control_plane_replacement_candidates_passes(self) -> None:
        r1 = self._run("audit_admin_gravity.py", "--strict")
        self.assertEqual(r1.returncode, 0, msg=r1.stderr)
        r2 = self._run("verify_control_plane_replacement_candidates.py")
        self.assertEqual(r2.returncode, 0, msg=r2.stderr + r2.stdout)
        r3 = self._run("verify_admin_replacement_roadmap.py")
        self.assertEqual(r3.returncode, 0, msg=r3.stderr + r3.stdout)
