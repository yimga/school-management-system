#!/usr/bin/env python3
"""Fail closed when approved governed outcome surfaces regress."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    failures: list[str] = []
    governed = {
        "templates/marketplace/templates_apply_confirm.html": (
            'data-rmc-governed-outcome="template-apply"',
            "rmc-governed-hero", "rmc-governed-layout", "rmc-governed-facts",
            "data-rmc-template-apply-form", "data-rmc-confirm", "{% csrf_token %}",
            "template_marketplace:preview", "template_marketplace:customize",
            "template_marketplace:rollback", "studio_os:launch",
        ),
        "templates/marketplace/templates_rollback_confirm.html": (
            'data-rmc-governed-outcome="template-rollback"', "rmc-governed-layout",
            "{% csrf_token %}", "data-rmc-confirm",
        ),
        "templates/marketplace/templates_customize.html": (
            'data-rmc-governed-outcome="template-customize"', "rmc-governed-layout",
            "{% csrf_token %}", "customizations_json",
        ),
        "templates/platform_runtime/blueprint_apply.html": (
            'data-rmc-governed-outcome="blueprint-apply"', "rmc-governed-layout",
            "{% csrf_token %}", 'name="action" value="request_approval"',
        ),
        "templates/platform_runtime/blueprint_rollback.html": (
            'data-rmc-governed-outcome="blueprint-rollback"', "rmc-governed-layout",
            "{% csrf_token %}", 'name="confirm" value="yes"',
        ),
    }
    for path, required in governed.items():
        text = read(path)
        for token in required:
            if token not in text:
                failures.append(f"{path}: missing {token}")
        if "|pprint" in text:
            failures.append(f"{path}: raw backend dictionary exposed")
        if "default:_(" in text:
            failures.append(f"{path}: unsafe translated filter argument")

    css = read("static/css/rmc-governed-outcome.css")
    for token in ("grid-template-columns", "@media(max-width:64rem)",
                  "@media(max-width:40rem)", "prefers-reduced-motion"):
        if token not in css:
            failures.append(f"shared CSS missing {token}")
    for base in ("templates/portal_base.html", "templates/control_plane_base.html"):
        if "rmc-governed-outcome.css" not in read(base):
            failures.append(f"{base}: shared CSS not mounted")
    sw = read("static/js/service-worker.js")
    if '"/static/css/rmc-governed-outcome.css"' not in sw:
        failures.append("service worker does not precache governed outcome CSS")

    if failures:
        print("GOVERNED_OUTCOME_SURFACES_FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print(f"GOVERNED_OUTCOME_SURFACES_PASS surfaces={len(governed)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
