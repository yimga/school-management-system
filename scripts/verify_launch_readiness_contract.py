#!/usr/bin/env python3
"""Fail closed on launch shell, classification and direct-action regressions."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    failures: list[str] = []
    service = read("apps/setup_studio/services.py")
    embed = read("templates/customersuccess/guided_onboarding_embed.html")
    canvas = read("templates/studio_os/partials/workspace/launch_canvas.html")
    view = read("apps/studio_os/views.py")
    required = {
        "service": (service, '"requirement_level": "required_with_waiver"',
                    '"requirement_level": "recommended"', '"is_skippable"',
                    '"is_blocker": key in {"plan_choice", "blueprint", "data_path"}'),
        "embed": (embed, "item.requirement_label", "Open data import",
                  "Review launch-without-roster option", "blocker.link",
                  "for item in launch_checklist %}"),
        "canvas": (canvas, "launch_standalone_url", "data-rmc-launch-standalone"),
        "view": (view, 'context["launch_standalone_url"]'),
    }
    for label, (text, *tokens) in required.items():
        for token in tokens:
            if token not in text:
                failures.append(f"{label}: missing {token}")
    if 'href="{{ launch_iframe_src }}" target="_blank"' in canvas:
        failures.append("iframe URL is still exposed as a standalone destination")
    if '"branding", "data_path"' in service:
        failures.append("branding still masquerades as a hard launch blocker")
    if failures:
        print("LAUNCH_READINESS_CONTRACT_FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("LAUNCH_READINESS_CONTRACT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
