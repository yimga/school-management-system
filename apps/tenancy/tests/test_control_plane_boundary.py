"""
RunMyCampus Blueprint D4: Explicit boundaries — tenant-facing apps must not import
control-plane models directly. They must use Policy Registry (get_effective_policy,
get_tenant_blueprint), marketplace services, or event emission instead.

This test fails if any module in a tenant app contains:
- from apps.customers.models import ...
- from apps.marketplace.models import ...
- from apps.policies.models import ...

Tenant apps: portal, academics, people, finance, evals, reports, communication.
Excluded: management/commands (infrastructure), tests (can mock), migrations.
"""
import os
from pathlib import Path

from django.test import TestCase


# Apps that serve tenant UI/API; they must not import control-plane ORM directly.
TENANT_APPS = ("portal", "student360", "academics", "people", "finance", "evals", "reports", "communication")

# Forbidden import patterns (tenant code must use resolver/registry/services, not ORM).
FORBIDDEN_PATTERNS = (
    "from apps.customers.models import",
    "from apps.marketplace.models import",
    "from apps.policies.models import",
)


def _get_app_path(app_label: str) -> Path | None:
    from django.apps import apps
    try:
        app_config = apps.get_app_config(app_label)
        return Path(app_config.path)
    except LookupError:
        return None


def _collect_py_files(app_path: Path, exclude_dirs: tuple = ("migrations", "management", "tests",)) -> list[Path]:
    files = []
    for root, _dirs, filenames in os.walk(app_path):
        rel = Path(root)
        if any(part in exclude_dirs for part in rel.parts):
            continue
        for name in filenames:
            if name.endswith(".py") and not name.startswith("__"):
                files.append(Path(root) / name)
    return files


def _file_contains_forbidden_imports(path: Path) -> list[str]:
    found = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pattern in FORBIDDEN_PATTERNS:
                if pattern in stripped:
                    found.append(pattern)
                    break
    except OSError:
        pass
    return found


class ControlPlaneBoundaryTestCase(TestCase):
    """D4: Tenant apps must not import control-plane models; use Policy Registry / services only."""

    def test_tenant_apps_do_not_import_control_plane_models(self):
        from django.apps import apps
        base = Path(apps.get_app_config("tenancy").path).parent
        violations = []
        for app_label in TENANT_APPS:
            app_path = base / app_label
            if not app_path.is_dir():
                continue
            for py_path in _collect_py_files(app_path):
                rel_path = py_path.relative_to(base)
                found = _file_contains_forbidden_imports(py_path)
                if found:
                    violations.append((str(rel_path), found))
        self.assertFalse(
            violations,
            "Tenant apps must not import control-plane models. Use get_effective_policy, "
            "get_tenant_blueprint, marketplace services, or emit_event instead. Violations: %s"
            % (violations,),
        )
