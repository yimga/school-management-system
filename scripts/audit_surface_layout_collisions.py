"""Fail on layout contracts that detach or vertically crush platform surfaces."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
GRAMMAR = ROOT / "static/css/rmc-class-grammar.css"
MIGRATION_CSS = ROOT / "static/css/migration-cloud-ui.css"


def main() -> int:
    findings: list[str] = []
    structural = re.compile(
        r'<(?:main|section|article|div)\b[^>]*class="[^"]*(?<![\w-])rmc-mapping(?![\w-])[^"]*"',
        re.IGNORECASE,
    )

    for path in TEMPLATES.rglob("*.html"):
        source = path.read_text(encoding="utf-8", errors="ignore")
        if structural.search(source):
            findings.append(f"{path.relative_to(ROOT)}: structural .rmc-mapping class collision")

    bundle = (TEMPLATES / "migration_cloud/bundle_detail.html").read_text(encoding="utf-8")
    for marker in (
        'class="rmc-card rmc-mapping-workbench rmc-reveal"',
        'data-rmc-native-workbench-table="1"',
    ):
        if marker not in bundle:
            findings.append(f"templates/migration_cloud/bundle_detail.html: missing {marker}")
    for forbidden in (
        'data-rmc-row-detail-auto="1"',
        'data-rmc-row-detail-table="1"',
        'class="rmc-card rmc-mapping rmc-reveal"',
    ):
        if forbidden in bundle:
            findings.append(
                f"templates/migration_cloud/bundle_detail.html: forbidden {forbidden}"
            )

    grammar = GRAMMAR.read_text(encoding="utf-8")
    migration_css = MIGRATION_CSS.read_text(encoding="utf-8")
    for marker in (
        ".rmc-button-row > :is(form, a, button)",
        ".rmc-button-row > form",
        ":has(> .rmc-data-table)",
    ):
        if marker not in grammar:
            findings.append(f"static/css/rmc-class-grammar.css: missing {marker}")
    for marker in (
        ".rmc-page--migration-cloud-detail .rmc-mapping-workbench",
        "display: block",
    ):
        if marker not in migration_css:
            findings.append(f"static/css/migration-cloud-ui.css: missing {marker}")

    if findings:
        print("SURFACE_LAYOUT_COLLISION_AUDIT_FAIL")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("SURFACE_LAYOUT_COLLISION_AUDIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
