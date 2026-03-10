import ast
from pathlib import Path

from django.test import SimpleTestCase

from config import settings as project_settings


LEGACY_MIXED_SHARED_APPS = {"accounts", "schools", "siteconfig"}


def _schema_app_lists() -> tuple[set[str], set[str]]:
    settings_path = project_settings.BASE_DIR / "config" / "settings.py"
    tree = ast.parse(settings_path.read_text(encoding="utf-8"))
    shared_apps = []
    tenant_apps = []

    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign) or not isinstance(stmt.value, (ast.List, ast.Tuple)):
                continue
            target_names = [target.id for target in stmt.targets if isinstance(target, ast.Name)]
            values = [
                elt.value
                for elt in stmt.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            ]
            if "SHARED_APPS" in target_names:
                shared_apps = values
            if "TENANT_APPS" in target_names:
                tenant_apps = values

    shared_labels = {
        app.split(".")[-1]
        for app in shared_apps
        if app == "emis" or app.startswith("apps.")
    }
    tenant_labels = {
        app.split(".")[-1]
        for app in tenant_apps
        if app.startswith("apps.")
    }
    return shared_labels, tenant_labels


class SharedMigrationDependencyBoundaryTests(SimpleTestCase):
    def test_only_legacy_mixed_shared_apps_depend_on_tenant_migrations(self):
        shared_apps, tenant_apps = _schema_app_lists()
        base = project_settings.BASE_DIR / "apps"
        violations = []

        for path in base.glob("*/migrations/*.py"):
            app_label = path.parts[-3]
            if app_label not in shared_apps:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef) or node.name != "Migration":
                    continue
                for stmt in node.body:
                    if not isinstance(stmt, ast.Assign) or not isinstance(stmt.value, (ast.List, ast.Tuple)):
                        continue
                    if not any(isinstance(target, ast.Name) and target.id == "dependencies" for target in stmt.targets):
                        continue
                    for elt in stmt.value.elts:
                        if not isinstance(elt, ast.Tuple) or not elt.elts:
                            continue
                        first = elt.elts[0]
                        if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
                            continue
                        dep_label = first.value.split(".")[-1]
                        if dep_label in tenant_apps and app_label not in LEGACY_MIXED_SHARED_APPS:
                            violations.append((app_label, path.name, dep_label))

        self.assertEqual(
            violations,
            [],
            msg=(
                "Shared apps must not gain new tenant-migration dependencies. "
                f"Only legacy mixed apps are temporarily allowed: {sorted(LEGACY_MIXED_SHARED_APPS)}. "
                f"Violations: {violations}"
            ),
        )
