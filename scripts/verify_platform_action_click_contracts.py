#!/usr/bin/env python3
"""Platform-wide action and remediation click-contract gate."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = ROOT / "templates"
APP_ROOT = ROOT / "apps"
DEAD_HREF_RE = re.compile(r"href\s*=\s*(['\"])\s*(?:#|javascript:void\(0\))\s*\1", re.I)
DEAD_HREF_ASSIGNMENT_RE = re.compile(
    r"\.href\s*=\s*(['\"])\s*#\s*\1\s*(?:;|$)", re.I | re.M
)
ACTION_FILE_RE = re.compile(
    r"(?:action|recommend|remediat|repair|blocker|readiness|setup|workflow|zero_friction|config)",
    re.I,
)
VAGUE_CTA_RE = re.compile(r"['\"]cta_label['\"]\s*:\s*['\"](?:Continue|Resolve|Fix)['\"]")
FORBIDDEN_DETOURS = {
    "/school/finance/": "/finance/invoices/?status=overdue",
    "/school/settings/storage/": "/siteconfig/billing/plan/?focus=storage",
}


def _first_party_python() -> list[Path]:
    return [
        path
        for path in APP_ROOT.rglob("*.py")
        if "migrations" not in path.parts and "tests" not in path.parts
    ]


def scan() -> list[str]:
    errors: list[str] = []
    for path in TEMPLATE_ROOT.rglob("*.html"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in DEAD_HREF_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            errors.append(f"{path.relative_to(ROOT)}:{line}: dead action href")
        for match in DEAD_HREF_ASSIGNMENT_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            errors.append(f"{path.relative_to(ROOT)}:{line}: script restores a dead href")

    for path in (ROOT / "static").rglob("*.js"):
        if "vendor" in path.parts or "dist" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in DEAD_HREF_ASSIGNMENT_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            errors.append(f"{path.relative_to(ROOT)}:{line}: script assigns a dead href")

    for path in _first_party_python():
        text = path.read_text(encoding="utf-8", errors="replace")
        rel = path.relative_to(ROOT)
        for detour, replacement in FORBIDDEN_DETOURS.items():
            if detour in text:
                errors.append(
                    f"{rel}: generic/non-routable detour {detour!r}; use {replacement!r}"
                )
        if ACTION_FILE_RE.search(path.name):
            for match in VAGUE_CTA_RE.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                errors.append(
                    f"{rel}:{line}: blocker CTA must name the action, not a vague verb"
                )
    return errors


def main() -> int:
    errors = scan()
    if errors:
        print("PLATFORM_ACTION_CLICK_CONTRACT_FAIL")
        for error in errors[:100]:
            print(f"  - {error}")
        return 1
    print("PLATFORM_ACTION_CLICK_CONTRACT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
