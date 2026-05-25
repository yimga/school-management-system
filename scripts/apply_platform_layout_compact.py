#!/usr/bin/env python3
"""
Platform-wide layout compact pass — all /super/, manager /admin/ CP pages, tenant backend.

Mechanical fixes (no hand-picking routes):
- container-fluid py-4/py-5 -> py-2 on operational surfaces (wizards/open density exempt)
- data-rmc-operational-workbench on operational-workbench archetype roots
- mb-5 -> mb-3 on page roots inside control-plane templates
- strip nested content-max-* clamps on CP templates
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

EXTENDS_CP = re.compile(
    r'extends\s+["\']control_plane_base\.html["\']',
    re.IGNORECASE,
)
EXTENDS_PORTAL = re.compile(
    r'extends\s+["\']portal_base\.html["\']',
    re.IGNORECASE,
)
EXTENDS_BACKEND = re.compile(
    r'extends\s+["\']backend_base[^"\']*\.html["\']',
    re.IGNORECASE,
)

CP_PATH_PREFIXES = (
    "templates/schools/super_",
    "templates/schools/billing_dashboard.html",
    "templates/schools/manager_",
    "templates/marketplace/",
    "templates/platform_runtime/",
    "templates/observability/",
    "templates/orchestration/",
    "templates/migration_cloud/",
    "templates/customersuccess/",
    "templates/apicenter/super/",
    "templates/schoolops/super/",
    "templates/schoolops/operator/",
    "templates/siteconfig/super/",
    "templates/siteconfig/operator_control_plane",
    "templates/integrations_marketplace/manager_",
    "templates/sales/",
    "templates/feedback/voice_of_customer",
    "templates/feedback/product_roadmap",
    "templates/automation/workflow_template_gallery",
    "templates/lifecycle/",
    "templates/archetypes/cp_",
    "templates/studio_os/shell_control_plane",
    "templates/backend_base_manager",
    "templates/siteconfig/partials/",
    "templates/customersuccess/",
    "templates/studio_os/partials/",
    "templates/evals/",
    "templates/finance/",
    "templates/people/",
    "templates/schoolops/",
    "templates/accounts/",
    "templates/automation/",
    "templates/compliance/",
    "templates/events/",
    "templates/reports/",
    "templates/portal/",
    "templates/parent/",
    "templates/academics/",
)

WIZARD_EXEMPT = (
    "wizard",
    "setup-studio",
    "checkout",
    "onboard",
)
OPEN_DENSITY = 'data-rmc-density="open"'

ARCHETYPE_RE = re.compile(
    r'(<[^>]+data-page-archetype="operational-workbench")(?=")(?![^>]*data-rmc-operational-workbench)'
)
CONTENT_MAX_RE = re.compile(r"\s*content-max-(?:520|640|960|1200|narrow)\b")


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def _in_scope(path: Path) -> bool:
    rel = _rel(path)
    if rel.startswith("templates/marketing/"):
        return False
    if rel.startswith("templates/auth/"):
        return False
    if rel.startswith("templates/errors/"):
        return False
    if any(rel.startswith(p) for p in CP_PATH_PREFIXES):
        return True
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    if EXTENDS_CP.search(text) or EXTENDS_PORTAL.search(text) or EXTENDS_BACKEND.search(text):
        return True
    if 'data-page-archetype="operational-workbench"' in text:
        return True
    return False


def _exempt_py_compact(text: str, rel: str) -> bool:
    if OPEN_DENSITY in text:
        return True
    lower = rel.lower()
    if any(x in lower for x in WIZARD_EXEMPT):
        return True
    if "super_dashboard.html" in rel or "customersuccess/super_dashboard" in rel:
        return True
    return False


def patch_file(path: Path) -> dict[str, int]:
    rel = _rel(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    original = text
    stats = {
        "py4": 0,
        "py5": 0,
        "marker": 0,
        "mb5": 0,
        "content_max": 0,
    }

    if 'data-page-archetype="operational-workbench"' in text:
        if 'data-rmc-operational-workbench="1"' not in text:

            def add_marker(m: re.Match[str]) -> str:
                return m.group(1) + '" data-rmc-operational-workbench="1"'

            text, n = ARCHETYPE_RE.subn(add_marker, text, count=1)
            stats["marker"] += n

    if not _exempt_py_compact(text, rel):
        if "container-fluid py-4" in text:
            count = text.count("container-fluid py-4")
            text = text.replace("container-fluid py-4", "container-fluid py-2")
            stats["py4"] += count
        if "container-fluid py-5" in text:
            count = text.count("container-fluid py-5")
            text = text.replace("container-fluid py-5", "container-fluid py-2")
            stats["py5"] += count

    if (
        EXTENDS_CP.search(text)
        or EXTENDS_PORTAL.search(text)
        or any(rel.startswith(p) for p in CP_PATH_PREFIXES)
        or rel.startswith("templates/siteconfig/")
        or rel.startswith("templates/studio_os/")
    ):
        new_text, n = CONTENT_MAX_RE.subn("", text)
        if n:
            text = new_text
            stats["content_max"] += n

        # Page-root margin bloat on CP templates only
        if 'class="container-fluid py-2' in text or "container-fluid py-2" in text:
            before = text
            text = re.sub(
                r'(<div class="container-fluid[^"]*)\bmb-5\b',
                r"\1mb-3",
                text,
                count=3,
            )
            if text != before:
                stats["mb5"] += 1

    if text != original:
        path.write_text(text, encoding="utf-8", newline="\n")
    return stats


def main() -> int:
    totals = {"py4": 0, "py5": 0, "marker": 0, "mb5": 0, "content_max": 0, "files": 0}
    for path in sorted(TEMPLATES.rglob("*.html")):
        if not _in_scope(path):
            continue
        stats = patch_file(path)
        if any(stats.values()):
            totals["files"] += 1
            for k in ("py4", "py5", "marker", "mb5", "content_max"):
                totals[k] += stats[k]
    print(
        "apply_platform_layout_compact:"
        f" files={totals['files']}"
        f" py4={totals['py4']}"
        f" py5={totals['py5']}"
        f" markers={totals['marker']}"
        f" mb5={totals['mb5']}"
        f" content_max={totals['content_max']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
