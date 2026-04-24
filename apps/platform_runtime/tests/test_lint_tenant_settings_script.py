from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.platform_runtime.tests.support.repo_tree import write_repo_file
from apps.platform_runtime.tests.support.script_loading import load_repo_script


class LintTenantSettingsScriptTests(SimpleTestCase):
    def _load_script_module(self):
        return load_repo_script(
            "scripts/lint_tenant_settings.py",
            "lint_tenant_settings_script_test_module",
        )

    def _write_fixture_repo(self, root: Path, *, app_rel: str, content: str) -> None:
        (root / ".git").mkdir(parents=True, exist_ok=True)  # make tracked-file path eligible
        write_repo_file(root, app_rel, content)

    def test_get_solo_violation_fails_without_exit_zero(self):
        module = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._write_fixture_repo(
                repo,
                app_rel="apps/portal/bad_settings.py",
                content="\n".join(
                    [
                        "from apps.siteconfig.models import SiteSettings",
                        "",
                        "def f():",
                        "    return SiteSettings.get_solo()",
                        "",
                    ]
                ),
            )
            with patch.object(
                module, "_tracked_file_relpaths", return_value=frozenset({"apps/portal/bad_settings.py"})
            ):
                rc = module.main(["--check-get-solo-only", "--base", str(repo)])
        self.assertEqual(rc, 1)

    def test_sitesettings_objects_violation_fails(self):
        module = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._write_fixture_repo(
                repo,
                app_rel="apps/finance/bad_orm.py",
                content="\n".join(
                    [
                        "from apps.siteconfig.models import SiteSettings",
                        "",
                        "def f():",
                        "    return SiteSettings.objects.filter(pk=1).first()",
                        "",
                    ]
                ),
            )
            with patch.object(
                module, "_tracked_file_relpaths", return_value=frozenset({"apps/finance/bad_orm.py"})
            ):
                rc = module.main(
                    ["--check-sitesettings-orm-in-tenant-apps", "--base", str(repo)]
                )
        self.assertEqual(rc, 1)

    def test_sitesettings_objects_order_by_chain_fails(self):
        """Chained ORM (e.g. .order_by().first()) must be flagged, not only .get()/.filter()."""
        module = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._write_fixture_repo(
                repo,
                app_rel="apps/portal/bad_orm.py",
                content="\n".join(
                    [
                        "from apps.siteconfig.models import SiteSettings",
                        "",
                        "def f():",
                        '    return SiteSettings.objects.order_by("pk").first()',
                        "",
                    ]
                ),
            )
            with patch.object(
                module, "_tracked_file_relpaths", return_value=frozenset(
                    {"apps/portal/bad_orm.py"}
                )
            ):
                rc = module.main(
                    ["--check-sitesettings-orm-in-tenant-apps", "--base", str(repo)]
                )
        self.assertEqual(rc, 1)

    def test_sitesettings_site_save_update_fields_fails(self):
        module = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._write_fixture_repo(
                repo,
                app_rel="apps/accounts/bad_slim_save.py",
                content="\n".join(
                    [
                        "def f(site):",
                        '    site.save(update_fields=["maintenance_mode"])',
                        "",
                    ]
                ),
            )
            with patch.object(
                module, "_tracked_file_relpaths", return_value=frozenset(
                    {"apps/accounts/bad_slim_save.py"}
                )
            ):
                rc = module.main(
                    ["--check-sitesettings-orm-in-tenant-apps", "--base", str(repo)]
                )
        self.assertEqual(rc, 1)

    def test_report_allowlisted_is_zero_for_fixture_repo(self):
        module = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / ".git").mkdir(parents=True, exist_ok=True)
            with patch.object(module, "_tracked_file_relpaths", return_value=frozenset()):
                with patch("builtins.print") as mock_print:
                    rc = module.main(["--report-allowlisted", "--base", str(repo)])
        self.assertEqual(rc, 0)
        out = "\n".join(call.args[0] for call in mock_print.call_args_list if call.args)
        self.assertIn("Total allowlisted: 0", out)
