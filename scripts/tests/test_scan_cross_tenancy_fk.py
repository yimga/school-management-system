"""Lock the cross-tenancy FK gate.

The gate is only worth having if it (a) FIRES on a shared->tenant FK, and
(b) stays SILENT on tenant->shared, which is the normal, legal pattern used by
roughly 200 existing migrations (every `<tenant model>.school -> schools.School`).
A gate that flagged those would be immediately disabled as noise.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "scan_cross_tenancy_fk", SCRIPTS / "scan_cross_tenancy_fk.py"
)
mod = importlib.util.module_from_spec(_spec)
sys.modules["scan_cross_tenancy_fk"] = mod
_spec.loader.exec_module(mod)


TENANCY = {"schools": "shared", "accounts": "shared", "finance": "tenant", "people": "tenant"}

SHARED_TO_TENANT = '''
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    operations = [
        migrations.AddField(
            model_name="advancementgift",
            name="award_source",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to="finance.awardsource"),
        ),
    ]
'''

TENANT_TO_SHARED = '''
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    operations = [
        migrations.AddField(
            model_name="attendance",
            name="school",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to="schools.school"),
        ),
    ]
'''

SHARED_TO_TENANT_ALLOWED = '''
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    operations = [
        migrations.AddField(
            model_name="advancementgift",
            name="award_source",
            # cross-tenancy-fk-allow: reviewed - resolved in app code, not a real FK
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to="finance.awardsource"),
        ),
    ]
'''


class CrossTenancyFkScannerTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self._orig_apps = mod.APPS_DIR
        mod.APPS_DIR = self.root / "apps"
        self.addCleanup(self._restore)

    def _restore(self):
        mod.APPS_DIR = self._orig_apps
        self._tmp.cleanup()

    def _write(self, app: str, name: str, body: str):
        d = self.root / "apps" / app / "migrations"
        d.mkdir(parents=True, exist_ok=True)
        (d / "__init__.py").write_text("", encoding="utf-8")
        (d / name).write_text(body, encoding="utf-8")

    def test_fires_on_shared_to_tenant(self):
        """The real defect: schools(shared) -> finance(tenant)."""
        self._write("schools", "0067_x.py", SHARED_TO_TENANT)
        findings = mod.scan(TENANCY)
        self.assertEqual(len(findings), 1, findings)
        self.assertEqual(findings[0]["source_app"], "schools")
        self.assertEqual(findings[0]["target_app"], "finance")

    def test_silent_on_tenant_to_shared(self):
        """The legal, ubiquitous direction must never be flagged."""
        self._write("people", "0001_x.py", TENANT_TO_SHARED)
        self.assertEqual(mod.scan(TENANCY), [])

    def test_allow_marker_suppresses(self):
        self._write("schools", "0067_x.py", SHARED_TO_TENANT_ALLOWED)
        self.assertEqual(mod.scan(TENANCY), [])

    def test_unknown_app_is_ignored(self):
        self._write("schools", "0001_x.py", SHARED_TO_TENANT.replace("finance.", "django_celery_beat."))
        self.assertEqual(mod.scan(TENANCY), [])

    def test_key_is_line_insensitive(self):
        a = {"path": "p", "source_app": "schools", "target_app": "finance", "line": 10}
        b = {"path": "p", "source_app": "schools", "target_app": "finance", "line": 99}
        self.assertEqual(mod._key(a), mod._key(b))

    def test_tenancy_map_reads_real_settings(self):
        """Calibration against the live settings, not a fixture."""
        tenancy = mod.load_tenancy_map()
        self.assertEqual(tenancy.get("schools"), "shared")
        self.assertEqual(tenancy.get("finance"), "tenant")
        self.assertEqual(tenancy.get("schoolops"), "tenant")

    def test_live_tree_still_detects_the_known_deploy_blocker(self):
        """schools.0067 must remain visible — it is why this gate exists."""
        mod.APPS_DIR = self._orig_apps  # scan the REAL tree, not the temp fixture
        findings = mod.scan(mod.load_tenancy_map())
        paths = {f["path"] for f in findings}
        self.assertIn(
            "apps/schools/migrations/0067_advancementgift_award_source_and_more.py",
            paths,
        )


if __name__ == "__main__":
    unittest.main()
