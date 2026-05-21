#!/usr/bin/env python3
"""Replace Bootstrap text-white/text-dark in class attributes only (main-content templates)."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

TARGET_DIRS = (
    REPO / "templates/siteconfig",
    REPO / "templates/schools",
    REPO / "templates/platform_runtime",
    REPO / "templates/admin",
    REPO / "templates/portal",
)

SKIP_NAME_PARTS = (
    "control_plane_sidebar",
    "manager_operator_topbar",
    "marketing",
    "offcanvas",
    "navbar",
    "statement-header",
)

CLASS_ATTR = re.compile(
    r'class="([^"]*)"',
    re.MULTILINE,
)

UTILITIES = (
    "text-white-75",
    "text-white-50",
    "text-white",
    "text-dark",
)

DARK_SURFACE_TOKENS = ("bg-dark", "bg-secondary", "bg-black", "bg-primary")
LIGHT_BADGE_TOKENS = ("bg-light", "bg-white", "bg-warning")


def should_process(path: Path) -> bool:
    if path.suffix not in {".html", ".htm"}:
        return False
    name = path.name.lower()
    if any(part in name for part in SKIP_NAME_PARTS):
        return False
    if path.parent.name == "schools" and name.startswith("super_"):
        return True
    if path.parent.name in {"siteconfig", "platform_runtime"}:
        return True
    if path.parent.name == "portal" and name in {
        "offline_sync_queue.html",
        "kb_home.html",
    }:
        return True
    if path.parent.name == "admin":
        return name.endswith(".html") and "login" not in name
    return False


def normalize_class_value(value: str) -> str:
    tokens = value.split()
    keep_white = any(t in tokens for t in DARK_SURFACE_TOKENS)
    keep_dark = any(t in tokens for t in LIGHT_BADGE_TOKENS)
    out: list[str] = []
    for token in tokens:
        if not token:
            continue
        if token in UTILITIES:
            if token.startswith("text-white") and keep_white:
                out.append(token)
            elif token == "text-dark" and keep_dark:
                out.append(token)
            continue
        out.append(token)
    return " ".join(out)


def transform(content: str) -> str:
    def repl(match: re.Match[str]) -> str:
        cleaned = normalize_class_value(match.group(1))
        if not cleaned:
            return ""
        return f'class="{cleaned}"'

    return CLASS_ATTR.sub(repl, content)


def main() -> int:
    changed: list[Path] = []
    for base in TARGET_DIRS:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.html")):
            if not should_process(path):
                continue
            original = path.read_text(encoding="utf-8")
            updated = transform(original)
            if updated != original:
                path.write_text(updated, encoding="utf-8", newline="\n")
                changed.append(path)
    print(f"burndown_main_content_text_utilities: updated {len(changed)} file(s)")
    for path in changed[:50]:
        print(f"  - {path.relative_to(REPO)}")
    if len(changed) > 50:
        print(f"  ... and {len(changed) - 50} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
