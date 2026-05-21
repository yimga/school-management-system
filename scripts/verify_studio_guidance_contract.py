#!/usr/bin/env python3
"""Gate: Tenant Studio ships in-context guidance (Q&A panel + info tags)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = (
    ("apps/studio_os/studio_guidance.py", "MODE_GUIDANCE"),
    ("apps/studio_os/studio_guidance.py", "apply_studio_guidance_to_context"),
    ("templates/studio_os/partials/studio_guidance_panel.html", "Questions answered here"),
    ("templates/studio_os/partials/workspace/launch_rail.html", "rmc_info_tag.html"),
    ("static/css/studio-guidance.css", "rmc-studio-guidance"),
    ("templates/studio_os/partials/shell_extrastyle.html", "studio-guidance.css"),
    ("templates/studio_os/modes/launch.html", "studio_guidance_panel.html"),
    ("apps/studio_os/views.py", "apply_studio_guidance_to_context"),
)


def main() -> int:
    errors = []
    for rel, token in REQUIRED:
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing {rel}")
            continue
        if token not in path.read_text(encoding="utf-8"):
            errors.append(f"{rel} missing {token!r}")

    launch_rail = ROOT / "templates/studio_os/partials/workspace/launch_rail.html"
    if launch_rail.is_file() and "rmc_info_tag.html" not in launch_rail.read_text(encoding="utf-8"):
        errors.append("launch_rail.html missing rmc_info_tag include")

    if errors:
        print("verify_studio_guidance_contract: FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("verify_studio_guidance_contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
