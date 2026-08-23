"""Coverage for ``scan_admin_registered_on_unmounted_site``.

Stdlib only, like the scanner: it runs in the deps-free boundary job and must not
need Django to answer "is this admin reachable".
"""

from __future__ import annotations

import importlib.util
import pathlib
import tempfile
import unittest

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = SCRIPTS_DIR.parent


def _load():
    spec = importlib.util.spec_from_file_location(
        "scan_admin_registered_on_unmounted_site",
        SCRIPTS_DIR / "scan_admin_registered_on_unmounted_site.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScanAdminUnmountedSiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load()

    def _tree(self, admin_source: str, urls_source: str):
        tmp = pathlib.Path(tempfile.mkdtemp())
        (tmp / "config").mkdir()
        (tmp / "config" / "urls.py").write_text(urls_source, encoding="utf-8")
        app = tmp / "apps" / "widget"
        app.mkdir(parents=True)
        (app / "admin.py").write_text(admin_source, encoding="utf-8")
        return tmp

    _URLS = (
        "from django.urls import path\n"
        "from config.admin import tenant_admin_site, platform_admin_site\n"
        "urlpatterns = [\n"
        "    path('admin/', tenant_admin_site.urls),\n"
        "    path('ops/', platform_admin_site.urls),\n"
        "]\n"
    )

    def test_it_discovers_the_mounted_sites_from_the_urlconf(self):
        tmp = self._tree("", self._URLS)
        names = self.mod.mounted_site_names(tmp / "config")
        self.assertEqual(names, {"tenant_admin_site", "platform_admin_site"})

    def test_a_decorator_with_no_site_is_a_finding(self):
        tmp = self._tree(
            "from django.contrib import admin\n"
            "@admin.register(Thing)\n"
            "class ThingAdmin(admin.ModelAdmin):\n"
            "    pass\n",
            self._URLS,
        )
        found = self.mod.collect(tmp / "apps", self.mod.mounted_site_names(tmp / "config"))
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["symbol"], "ThingAdmin")

    def test_a_decorator_naming_a_mounted_site_is_clean(self):
        tmp = self._tree(
            "from django.contrib import admin\n"
            "@admin.register(Thing, site=tenant_admin_site)\n"
            "class ThingAdmin(admin.ModelAdmin):\n"
            "    pass\n",
            self._URLS,
        )
        self.assertEqual(
            self.mod.collect(tmp / "apps", self.mod.mounted_site_names(tmp / "config")), []
        )

    def test_a_decorator_naming_an_UNMOUNTED_site_is_a_finding(self):
        """The whole point: naming a site is not enough, it has to be routed."""
        tmp = self._tree(
            "from django.contrib import admin\n"
            "@admin.register(Thing, site=some_other_site)\n"
            "class ThingAdmin(admin.ModelAdmin):\n"
            "    pass\n",
            self._URLS,
        )
        found = self.mod.collect(tmp / "apps", self.mod.mounted_site_names(tmp / "config"))
        self.assertEqual(len(found), 1, found)
        self.assertEqual(found[0]["site"], "some_other_site")

    def test_a_bare_admin_site_register_call_is_a_finding(self):
        tmp = self._tree(
            "from django.contrib import admin\nadmin.site.register(Thing)\n", self._URLS
        )
        found = self.mod.collect(tmp / "apps", self.mod.mounted_site_names(tmp / "config"))
        self.assertEqual(len(found), 1, found)

    def test_an_allow_marker_waives_it(self):
        tmp = self._tree(
            "from django.contrib import admin\n"
            "# admin-site-allow: deliberately unrouted, kept for a management command\n"
            "@admin.register(Thing)\n"
            "class ThingAdmin(admin.ModelAdmin):\n"
            "    pass\n",
            self._URLS,
        )
        self.assertEqual(
            self.mod.collect(tmp / "apps", self.mod.mounted_site_names(tmp / "config")), []
        )

    def test_the_live_tree_matches_its_baseline(self):
        import json

        baseline = json.loads(
            (REPO_ROOT / "var" / "security-audit-baseline-admin-unmounted-site.json")
            .read_text(encoding="utf-8")
        )["finding_count"]
        found = self.mod.collect(
            REPO_ROOT / "apps", self.mod.mounted_site_names(REPO_ROOT / "config")
        )
        self.assertLessEqual(
            len(found),
            baseline,
            "a NEW admin registration landed on a site no urlconf mounts",
        )

    def test_the_live_tree_really_has_two_mounted_sites(self):
        # Calibration: if discovery returned nothing, every registration would
        # look like a finding and the baseline above would be meaningless.
        self.assertEqual(
            self.mod.mounted_site_names(REPO_ROOT / "config"),
            {"tenant_admin_site", "platform_admin_site"},
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
