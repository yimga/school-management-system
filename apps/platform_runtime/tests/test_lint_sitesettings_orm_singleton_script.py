from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.platform_runtime.tests.support.repo_tree import write_repo_file
from apps.platform_runtime.tests.support.script_loading import load_repo_script


class LintSiteSettingsOrmSingletonScriptTests(SimpleTestCase):
    def _load_script_module(self):
        return load_repo_script(
            "scripts/lint_sitesettings_orm_singleton.py",
            "lint_sitesettings_orm_singleton_script_test_module",
        )

    def test_ok_when_only_allowlisted_files_use_objects(self):
        module = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            write_repo_file(
                repo,
                "apps/siteconfig/models.py",
                "from apps.siteconfig.models import SiteSettings\nx = SiteSettings.objects.filter(pk=1)\n",
            )
            write_repo_file(
                repo,
                "apps/platform_runtime/helpers.py",
                "from apps.siteconfig.models import SiteSettings\nx = SiteSettings.objects.get(pk=1)\n",
            )
            rc = module.main(["--base", str(repo)])
        self.assertEqual(rc, 0)

    def test_fails_on_sitesettings_objects_outside_allowlist(self):
        module = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            write_repo_file(
                repo,
                "apps/api/bad_sitesettings.py",
                "from apps.siteconfig.models import SiteSettings\nSiteSettings.objects.all()\n",
            )
            rc = module.main(["--base", str(repo)])
        self.assertEqual(rc, 1)

    def test_skips_tests_and_migrations(self):
        module = self._load_script_module()
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            write_repo_file(
                repo,
                "apps/api/tests/test_ok.py",
                "from apps.siteconfig.models import SiteSettings\nSiteSettings.objects.all()\n",
            )
            write_repo_file(
                repo,
                "apps/api/migrations/0001_initial.py",
                "from apps.siteconfig.models import SiteSettings\nSiteSettings.objects.all()\n",
            )
            rc = module.main(["--base", str(repo)])
        self.assertEqual(rc, 0)
