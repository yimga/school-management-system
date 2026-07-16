from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SURFACE_DIRS = (
    "templates/studio_os",
    "templates/schools",
    "templates/super",
    "templates/siteconfig",
    "templates/platform_runtime",
    "templates/admin",
    "templates/teacher",
    "templates/people",
    "templates/finance",
    "templates/communication",
)
LONG_TEMPLATE_LINE_THRESHOLD = 180

SHARED_SHELL_TOKENS = (
    'extends "portal_base.html"',
    "extends 'portal_base.html'",
    'extends "backend_base_tenant.html"',
    "extends 'backend_base_tenant.html'",
    'extends "backend_base.html"',
    "extends 'backend_base.html'",
    'extends "control_plane_base.html"',
    "extends 'control_plane_base.html'",
    'extends "admin/base_site.html"',
    "extends 'admin/base_site.html'",
    'extends "admin/change_form.html"',
    "extends 'admin/change_form.html'",
    'extends "admin/change_list.html"',
    "extends 'admin/change_list.html'",
    'extends "studio_os/shell.html"',
    "extends 'studio_os/shell.html'",
)

COVERAGE_TOKENS = (
    'data-rmc-scroll-policy="paginate"',
    'data-rmc-operational-workbench="1"',
    'data-page-archetype="operational-workbench"',
    'data-rmc-studio-workspace="1"',
    'data-rmc-django-surface-canvas="tenant-backend"',
    'data-rmc-admin-content="canvas-first"',
    'data-rmc-cp-page-body="1"',
)


def _is_surface_template(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if rel.endswith(".svg.html"):
        return False
    return any(rel.startswith(prefix + "/") for prefix in SURFACE_DIRS)


def _partial_is_covered(rel: str) -> bool:
    return any(
        marker in rel
        for marker in (
            "/partials/",
            "/components/",
            "/includes/",
            "/workspace/",
            "/subpages/",
            "templates/admin/components/",
        )
    )


def main() -> int:
    errors: list[str] = []
    long_templates: list[tuple[int, str, str]] = []

    for path in sorted((ROOT / "templates").rglob("*.html")):
        if not _is_surface_template(path):
            continue
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        line_count = text.count("\n") + 1
        if line_count < LONG_TEMPLATE_LINE_THRESHOLD:
            continue

        extends_shared = any(token in text for token in SHARED_SHELL_TOKENS)
        has_scroll_marker = any(token in text for token in COVERAGE_TOKENS)
        is_partial = _partial_is_covered(rel)

        if extends_shared:
            status = "shared-shell"
        elif has_scroll_marker:
            status = "direct-marker"
        elif is_partial:
            status = "included-partial"
        else:
            status = "uncovered"
            errors.append(
                f"{rel}: {line_count} lines and no shared shell or long-surface marker"
            )
        long_templates.append((line_count, rel, status))

    css = (ROOT / "static/css/rmc-tenant-surface-scroll-contract.css").read_text(
        encoding="utf-8", errors="replace"
    )
    js = (ROOT / "static/js/rmc-tenant-surface-paginator.js").read_text(
        encoding="utf-8", errors="replace"
    )
    for token in (
        "[data-rmc-cp-page-body=\"1\"]",
        "[data-rmc-shell-root=\"django-admin\"]",
        ".studio-os__canvas",
        ".rmc-studio-workspace__main",
        "data-rmc-surface-page",
        "data-rmc-surface-scroll-zone",
    ):
        if token not in css and token not in js:
            errors.append(f"platform long-surface runtime missing {token}")

    if errors:
        print("PLATFORM_LONG_SURFACE_CONTRACT_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("PLATFORM_LONG_SURFACE_CONTRACT_PASS")
    print(f"  long_templates_audited: {len(long_templates)}")
    for line_count, rel, status in sorted(long_templates, reverse=True)[:12]:
        print(f"  - {rel}: {line_count} lines ({status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
