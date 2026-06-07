#!/usr/bin/env python3
"""
Phase 3 gate: navigation + command palette conformance on authenticated shells.

This check is intentionally narrow and mechanical:
- manager primary navigation must expose the canonical 8 IA labels
- manager authenticated shells must expose Ctrl+K command/search entry points
- Studio shell must expose its command palette contract

Run (from repo root):
  python scripts/verify_phase3_navigation_command_conformance.py
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent

_INCLUDE_RE = re.compile(r"""\{%\s*include\s+["']([^"']+)["']""")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_with_includes(path: Path, templates_root: Path, *, _seen: set[Path] | None = None) -> str:
    """Read ``path`` and inline-resolve every ``{% include "..." %}`` it contains.

    Resolves recursively so a base template's includes' includes also count.
    Cycles are broken by tracking visited paths. Missing includes are skipped
    silently (the verifier only checks for presence of marker strings, not
    correctness of every include chain).
    """
    if _seen is None:
        _seen = set()
    resolved = path.resolve()
    if resolved in _seen:
        return ""
    _seen.add(resolved)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    chunks = [text]
    for match in _INCLUDE_RE.finditer(text):
        rel = match.group(1).strip()
        child = (templates_root / rel)
        if child.is_file():
            chunks.append(_read_with_includes(child, templates_root, _seen=_seen))
    return "\n".join(chunks)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root to inspect (default: directory containing this script's parent).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"--base directory not found: {raw_base}")
    return base


def main(argv: list[str] | None = None) -> int:
    try:
        root = _resolve_base(parse_args(argv).base)
    except ValueError as exc:
        print(f"verify_phase3_navigation_command_conformance: {exc}", file=sys.stderr)
        return 1

    templates = root / "templates"
    errors: list[str] = []

    nav_partial = templates / "partials" / "control_plane_primary_nav.html"
    cp_base = templates / "control_plane_base.html"
    admin_bridge = templates / "components" / "admin_nav_bridge.html"
    manager_shell_js = root / "static" / "js" / "authenticated-shell-manager.js"
    studio_shell = templates / "studio_os" / "shell.html"

    for path in (nav_partial, cp_base, admin_bridge, manager_shell_js, studio_shell):
        if not path.is_file():
            errors.append(f"Missing required file: {path.relative_to(root).as_posix()}")

    if errors:
        print("verify_phase3_navigation_command_conformance: FAIL", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1

    nav_text = _read(nav_partial)
    # Canonical IA labels from Phase 3 mission.
    required_labels = (
        "Home",
        "Studio",
        "Operations",
        "Marketplace",
        "Analytics",
        "Migration",
        "Support",
        "Control",
    )
    for label in required_labels:
        if f"% trans '{label}'" not in nav_text and f'% trans "{label}"' not in nav_text:
            # Fallback: allow static literal if label is provided directly.
            if label not in nav_text:
                errors.append(
                    f"control_plane_primary_nav.html missing canonical nav label: {label}"
                )

    templates_root = root / "templates"
    cp_text = _read_with_includes(cp_base, templates_root)
    primary_nav_include = re.compile(
        r"""\{%\s*include\s+["']partials/control_plane_primary_nav\.html["']"""
    )
    if not primary_nav_include.search(cp_text):
        errors.append(
            "control_plane_base.html must include control_plane_primary_nav.html "
            "(directly or via consolidated header partials)."
        )
    if "id=\"cpSearchInput\"" not in cp_text:
        errors.append("control_plane_base.html missing manager search input id cpSearchInput (checked transitively through includes).")
    if "cpShowShortcutsHelp" not in cp_text:
        errors.append("control_plane_base.html missing keyboard shortcut help trigger (checked transitively through includes).")

    admin_bridge_text = _read_with_includes(admin_bridge, templates_root)
    if "id=\"cpSearchInputAdmin\"" not in admin_bridge_text:
        errors.append("admin_nav_bridge.html missing manager search input id cpSearchInputAdmin (checked transitively through includes).")
    if "cpShowShortcutsHelp" not in admin_bridge_text:
        errors.append("admin_nav_bridge.html missing keyboard shortcut help trigger (checked transitively through includes).")

    shell_js = _read(manager_shell_js)
    if "cpSearchInputAdmin" not in shell_js or "cpSearchInput" not in shell_js:
        errors.append(
            "authenticated-shell-manager.js must support both cpSearchInput and cpSearchInputAdmin."
        )
    if "runmycampus-cp-recent" not in shell_js:
        errors.append("authenticated-shell-manager.js missing cross-surface recent-nav key.")
    if (
        "/api/search/" not in shell_js
        and 'url("search")' not in shell_js
        and "readPlatformSearchUrl" not in shell_js
    ):
        errors.append("authenticated-shell-manager.js missing unified search endpoint wiring.")

    studio_text = _read(studio_shell)
    studio_markers = (
        "studio-command-palette-btn",
        "studio-cmd-palette",
        "studio-cmd-filter",
    )
    for marker in studio_markers:
        if marker not in studio_text:
            errors.append(f"studio_os/shell.html missing Studio command palette marker: {marker}")

    if "Ctrl+K" not in studio_text and "ctrlKey" not in studio_text:
        errors.append("studio_os/shell.html missing Ctrl+K command palette trigger contract.")

    if errors:
        print("verify_phase3_navigation_command_conformance: FAIL", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(
        "verify_phase3_navigation_command_conformance: PASS "
        "(primary IA labels + manager command/search + Studio command palette)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
