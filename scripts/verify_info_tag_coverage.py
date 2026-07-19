#!/usr/bin/env python3
"""
Verify 500X field catalog + 50X route explainers + shell wiring for page explain strips.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
MIN_CATALOG_KEYS = 500
MIN_SOVEREIGN_ROUTE_KEYS = 50

REQUIRED_SHELL_INCLUDES = (
    ROOT / "templates/base.html",
    ROOT / "templates/portal_base.html",
    ROOT / "templates/control_plane_base.html",
    ROOT / "templates/admin/base_site.html",
)

REQUIRED_SNIPPETS = (
    "components/rmc_page_explain_strip.html",
    "js/rmc-info-tag-auto.js",
    "context_processors.page_explain_context",
)


def _fail(msg: str) -> int:
    print(f"INFO_TAG_COVERAGE_FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    sys.path.insert(0, str(ROOT))
    import django

    django.setup()

    from apps.siteconfig.ui_field_help import catalog_entry_count
    from apps.siteconfig.ui_route_help import sovereign_route_entry_count

    count = catalog_entry_count()
    if count < MIN_CATALOG_KEYS:
        return _fail(f"catalog has {count} keys; need >= {MIN_CATALOG_KEYS}")

    route_count = sovereign_route_entry_count()
    if route_count < MIN_SOVEREIGN_ROUTE_KEYS:
        return _fail(f"sovereign route help has {route_count} keys; need >= {MIN_SOVEREIGN_ROUTE_KEYS}")

    route_help_src = (ROOT / "apps/siteconfig/ui_route_help.py").read_text(encoding="utf-8")
    if "ROUTE_HELP_SOVEREIGN_50X" not in route_help_src:
        return _fail("ui_route_help.py does not merge ROUTE_HELP_SOVEREIGN_50X")

    settings_path = ROOT / "config" / "settings.py"
    settings_text = settings_path.read_text(encoding="utf-8")
    if "page_explain_context" not in settings_text:
        return _fail("page_explain_context not registered in settings.py")

    tour_bootstrap = (ROOT / "templates/partials/rmc_tour_bootstrap.html").read_text(
        encoding="utf-8"
    )
    if "rmc-info-tag-auto.js" not in tour_bootstrap:
        return _fail("rmc-info-tag-auto.js not loaded in rmc_tour_bootstrap.html")

    for shell in REQUIRED_SHELL_INCLUDES:
        if not shell.is_file():
            return _fail(f"missing shell template {shell}")
        text = shell.read_text(encoding="utf-8")
        if "rmc_page_explain_strip.html" not in text:
            return _fail(f"{shell.name} missing rmc_page_explain_strip include")

    auto_js = ROOT / "static/js/rmc-info-tag-auto.js"
    if not auto_js.is_file():
        return _fail("static/js/rmc-info-tag-auto.js missing")

    print(f"INFO_TAG_COVERAGE_PASS catalog_keys={count} sovereign_routes={route_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
