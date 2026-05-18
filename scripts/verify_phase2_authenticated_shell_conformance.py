#!/usr/bin/env python3
"""
Phase 2 gate: authenticated shell template conformance.

Focused on high-traffic authenticated surfaces:
- /super/* templates (templates/schools/super_*.html)
- Studio OS templates (templates/studio_os/*.html, templates/studio_os/modes/*.html)

The gate enforces:
1) required base shell hierarchy
2) no direct use of control_plane_skeleton.html outside approved wrappers
3) explicit archetype marker presence on non-fragment /super templates
4) required shell marker contracts remain present in base templates

Run (from repo root):
  python scripts/verify_phase2_authenticated_shell_conformance.py
"""

from __future__ import annotations

import argparse
import fnmatch
from functools import lru_cache
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT

EXTENDS_RE = re.compile(r'\{\%\s*extends\s+"([^"]+)"\s*\%\}')

CONTROL_PLANE_SKELETON_ALLOWLIST = {
    "templates/control_plane_base.html",
    "templates/auth/admin_login.html",
    "templates/auth/manager_login.html",
    "templates/errors/403_control_plane.html",
    "templates/errors/404_control_plane.html",
    "templates/errors/500_control_plane.html",
    # Manager legacy surfaces (pre–control_plane_base migration); tracked, not shell drift.
    "templates/integrations_marketplace/manager_bulk_prestage.html",
    "templates/integrations_marketplace/manager_rollup.html",
    "templates/migration_cloud/anomaly_nudge.html",
    "templates/migration_cloud/assets.html",
    "templates/migration_cloud/attach_source.html",
    "templates/migration_cloud/bind_school.html",
    "templates/migration_cloud/bundle_detail.html",
    "templates/migration_cloud/conflicts.html",
    "templates/migration_cloud/console.html",
    "templates/migration_cloud/handoff_doc.html",
    "templates/migration_cloud/intake_new.html",
    "templates/migration_cloud/progress.html",
    "templates/schools/manager_feature_gap_register.html",
    "templates/schools/manager_feedback_loop.html",
    "templates/schools/manager_lane2_readiness.html",
    "templates/schools/manager_public_to_product_matrix.html",
}


@lru_cache(maxsize=1)
def _tracked_file_relpaths(root: Path) -> frozenset[str] | None:
    """Prefer tracked templates so local scratch shells do not fabricate failures."""
    try:
        proc = subprocess.run(
            ["git", "ls-files"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return None
    return frozenset(line.strip() for line in proc.stdout.splitlines() if line.strip())


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Phase 2 authenticated shell conformance."
    )
    parser.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root to inspect (default: directory containing this script's parent).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"Base path is not a directory: {base}")
    return base


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _extract_extends(path: Path) -> str | None:
    text = _read(path)
    match = EXTENDS_RE.search(text)
    return match.group(1) if match else None


def _iter_template_files(
    root: Path,
    scan_root: Path,
    *,
    pattern: str = "*.html",
    recursive: bool = False,
):
    tracked = _tracked_file_relpaths(root)
    if tracked is None:
        iterator = scan_root.rglob(pattern) if recursive else scan_root.glob(pattern)
        yield from iterator
        return

    prefix = scan_root.relative_to(root).as_posix()
    for relpath in sorted(tracked):
        rel = PurePosixPath(relpath)
        if recursive:
            if not relpath.startswith(prefix.rstrip("/") + "/") or not relpath.endswith(".html"):
                continue
        else:
            if rel.parent.as_posix() != prefix or not fnmatch.fnmatch(rel.name, pattern):
                continue
        path = root / relpath
        if path.is_file():
            yield path


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print("verify_phase2_authenticated_shell_conformance: FAIL", file=sys.stderr)
        print(f"  - {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []
    templates = root / "templates"

    portal_base = templates / "portal_base.html"
    control_plane_base = templates / "control_plane_base.html"
    admin_base = templates / "admin" / "base.html"

    portal_text = _read(portal_base)
    if "data-authenticated-surface=" not in portal_text or "rmc_shell.authenticated_surface" not in portal_text:
        errors.append(
            "portal_base.html missing authenticated-surface contract (rmc_shell.authenticated_surface)."
        )
    if "data-page-archetype" not in portal_text:
        errors.append("portal_base.html missing data-page-archetype contract.")

    cp_text = _read(control_plane_base)
    if "data-authenticated-surface=" not in cp_text or "rmc_shell.authenticated_surface" not in cp_text:
        errors.append(
            "control_plane_base.html missing authenticated-surface marker (rmc_shell.authenticated_surface)."
        )
    if "{% block cp_page_archetype %}" not in cp_text:
        errors.append("control_plane_base.html missing cp_page_archetype block.")

    admin_text = _read(admin_base)
    if 'data-authenticated-surface="{% if is_manager_host %}manager-control-plane{% else %}django-admin{% endif %}"' not in admin_text:
        errors.append("admin/base.html missing manager/django-admin authenticated-surface contract.")

    for path in _iter_template_files(root, templates / "schools", pattern="super_*.html"):
        rel = _relative(path, root)
        if "_fragment" in path.name:
            continue
        extends = _extract_extends(path)
        if extends != "control_plane_base.html":
            errors.append(f"{rel} must extend control_plane_base.html (found {extends!r}).")
            continue
        text = _read(path)
        if "data-page-archetype" not in text and "cp_page_archetype" not in text:
            errors.append(f"{rel} missing explicit archetype marker (data-page-archetype or cp_page_archetype).")

    studio_shell = templates / "studio_os" / "shell.html"
    if _extract_extends(studio_shell) != "portal_base.html":
        errors.append("templates/studio_os/shell.html must extend portal_base.html.")

    mode_dir = templates / "studio_os" / "modes"
    for path in _iter_template_files(root, mode_dir, pattern="*.html"):
        rel = _relative(path, root)
        extends = _extract_extends(path)
        if extends != "studio_os/shell.html":
            errors.append(f"{rel} must extend studio_os/shell.html (found {extends!r}).")

    for path in _iter_template_files(root, templates, pattern="*.html", recursive=True):
        rel = _relative(path, root)
        extends = _extract_extends(path)
        if extends == "control_plane_skeleton.html" and rel not in CONTROL_PLANE_SKELETON_ALLOWLIST:
            errors.append(
                f"{rel} directly extends control_plane_skeleton.html but is not allowlisted."
            )

    if errors:
        print("verify_phase2_authenticated_shell_conformance: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        "verify_phase2_authenticated_shell_conformance: PASS "
        "(shell markers + /super hierarchy + Studio hierarchy + skeleton allowlist)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
