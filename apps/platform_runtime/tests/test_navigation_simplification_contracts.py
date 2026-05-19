"""Control-plane navigation simplification contracts (batch 1281 final validation)."""

from __future__ import annotations

import ast
from pathlib import Path

from django.test import SimpleTestCase

from apps.schools.control_plane_nav import build_control_plane_nav

REPO_ROOT = Path(__file__).resolve().parents[3]
NAV_PATH = REPO_ROOT / "apps" / "schools" / "control_plane_nav.py"
OVERSIZE_THRESHOLD = 7

REQUIRED_REACHABILITY = (
    "studio_os",
    "super_schools_list",
    "super_migration",
    "super_customer_success",
)


class NavigationSimplificationContractsTests(SimpleTestCase):
    def test_no_oversize_nav_groups(self):
        src = NAV_PATH.read_text(encoding="utf-8")
        tree = ast.parse(src)
        oversize = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Name) and func.id == "add_group"):
                continue
            if len(node.args) < 2 or not isinstance(node.args[1], (ast.List, ast.Tuple)):
                continue
            name = node.args[0].value if isinstance(node.args[0], ast.Constant) else "?"
            count = sum(1 for el in node.args[1].elts if isinstance(el, ast.Dict))
            if count > OVERSIZE_THRESHOLD:
                oversize.append((name, count))
        self.assertEqual(
            oversize,
            [],
            f"Groups exceed {OVERSIZE_THRESHOLD} items: {oversize}",
        )

    def test_critical_hubs_linked_from_nav_builder(self):
        class _Req:
            path = "/super/"
            user = None
            urlconf = "config.manager_urls"

        nav = build_control_plane_nav(_Req())
        ids = []
        for group in nav:
            for item in group.get("items", []):
                ids.append(item.get("id"))
        for required in REQUIRED_REACHABILITY:
            self.assertIn(
                required,
                ids,
                f"control plane nav missing required id {required!r}",
            )

    def test_theme_experience_hub_in_catalog_paths(self):
        catalog = (REPO_ROOT / "apps/platform_runtime/administration_catalog.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("/siteconfig/theme-experience/hub/", catalog)
