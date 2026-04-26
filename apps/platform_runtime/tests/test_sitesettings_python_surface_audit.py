"""
``scripts/audit_sitesettings_python_surface.py`` — JSON contract + pattern classification (1035–1036).

Wired into Phase 6 (``verify_cursor_phase6_siteconfig_sitesettings``).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent
AUDIT = REPO / "scripts" / "audit_sitesettings_python_surface.py"
OUT = REPO / "docs" / "generated" / "sitesettings_python_surface_audit.json"


def _load_audit_mod():
    spec = importlib.util.spec_from_file_location("audit_sitesettings_python_surface", AUDIT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class SiteSettingsPythonSurfaceAuditTests(unittest.TestCase):
    def test_script_exits_zero_and_json_contract(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(AUDIT)],
            cwd=str(REPO),
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, proc.returncode, msg=proc.stdout + proc.stderr)
        self.assertTrue(OUT.is_file(), "audit must write JSON")
        data = json.loads(OUT.read_text(encoding="utf-8"))
        self.assertEqual(data.get("schema_version"), 2)
        self.assertIn("generated_at", data)
        self.assertIn("totals", data)
        self.assertIn("by_app", data)
        self.assertIn("per_file", data)
        self.assertIn("violations", data)
        self.assertIn("sitesettings_objects_violations", data)
        self.assertIn("top_files_by_sitesettings_word", data)
        self.assertIn("high_gravity_read_paths", data)
        for v in data.get("violations", []):
            self.assertIn("kind", v)
            self.assertIn("path", v)
        t = data["totals"]
        for k in (
            "sitesettings_word",
            "get_solo_paren",
            "sitesettings_objects",
            "get_effective_site_settings",
        ):
            self.assertIn(k, t, msg=t.keys())

    def test_scan_allows_class_level_allowlist(self) -> None:
        mod = _load_audit_mod()
        text = "from apps.siteconfig.models import SiteSettings\n"
        m = mod.scan_file_text(text + "x = 1\n")
        v = mod._violations_for_path("apps/siteconfig/models.py", m)  # noqa: SLF001
        self.assertEqual(v, [])

    def test_scan_rejects_unauthorized_import(self) -> None:
        mod = _load_audit_mod()
        text = "from apps.siteconfig.models import SiteSettings\n"
        m = mod.scan_file_text(text)
        v = mod._violations_for_path("apps/evals/bad.py", m)  # noqa: SLF001
        kinds = {x["kind"] for x in v}
        self.assertIn("import SiteSettings from apps.siteconfig.models", kinds)

    def test_scan_rejects_unauthorized_get_model(self) -> None:
        mod = _load_audit_mod()
        text = "def x():\n    SiteSettings = apps.get_model('siteconfig', 'SiteSettings')\n"
        m = mod.scan_file_text(text)
        v = mod._violations_for_path("apps/policies/bad.py", m)  # noqa: SLF001
        kinds = {x["kind"] for x in v}
        self.assertIn("get_model('siteconfig','SiteSettings')", kinds)

    def test_scan_rejects_unauthorized_objects(self) -> None:
        mod = _load_audit_mod()
        m = mod.scan_file_text("SiteSettings.objects.get(pk=1)\n")
        v = mod._violations_for_path("apps/portal/cheat.py", m)  # noqa: SLF001
        self.assertTrue(any(x["kind"] == "SiteSettings.objects" for x in v))

    def test_main_fails_on_injected_violation_sample_in_memory(self) -> None:
        mod = _load_audit_mod()
        srel = "apps/fake_injected/bad_sitesettings.py"
        m = mod.scan_file_text("from apps.siteconfig.models import SiteSettings\n")
        vlist = mod._violations_for_path(srel, m)  # noqa: SLF001
        self.assertTrue(vlist, "injected import must be a violation off-allowlist")
