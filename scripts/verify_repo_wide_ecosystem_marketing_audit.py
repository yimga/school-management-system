#!/usr/bin/env python3
"""
Repo-wide static audit for Program Phase 10 (ecosystem) + Phase 11 (marketing).

This closes the gap between “marker gates on a few files” and “every touched surface
in the monolith is enumerated and spine-checked” without a migrated DB.

What it does (deterministic, no Django import):
1. Inventories every Django app package under apps/ (directory with apps.py).
2. Counts all apps/**/*.py (excluding __pycache__) and all templates/**/*.html.
3. Verifies every apps/*/urls.py defines urlpatterns (UTF-8).
4. Verifies routing glue: super catalog + tenant catalog name hooks in config/super URLs.
5. AST-checks required callables on ecosystem Python modules (marketplace, packages,
   accounts migration/interop, siteconfig rollback).
6. Verifies every templates/marketplace/*.html (and partials) is non-trivial UTF-8.

Run: ``raise SystemExit(main(None))`` (optional ``--base``; default is this repository root).
"""

from __future__ import annotations

import argparse
import ast
from functools import lru_cache
from pathlib import Path, PurePosixPath
import subprocess
import sys

DEFAULT_REPO = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_REPO
APPS = ROOT / "apps"
TEMPLATES = ROOT / "templates"


@lru_cache(maxsize=1)
def _tracked_file_relpaths(root: Path) -> frozenset[str] | None:
    """Prefer tracked files so local scratch trees do not skew audit results."""
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=str(DEFAULT_REPO),
        help="Repository root (defaults to this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"Base path is not a directory: {base}")
    return base


def _configure_root(base: Path) -> None:
    global ROOT, APPS, TEMPLATES
    ROOT = base
    APPS = ROOT / "apps"
    TEMPLATES = ROOT / "templates"


def _fail(msg: str) -> None:
    print(f"FAIL repo-wide ecosystem/marketing audit: {msg}", file=sys.stderr)


def _iter_files(
    scan_root: Path,
    *,
    suffix: str | None = None,
    filename: str | None = None,
):
    tracked = _tracked_file_relpaths(ROOT)
    if tracked is None:
        if filename is not None:
            yield from scan_root.rglob(filename)
            return
        yield from scan_root.rglob(f"*{suffix}")
        return

    prefix = scan_root.relative_to(ROOT).as_posix().rstrip("/") + "/"
    for relpath in sorted(
        path
        for path in tracked
        if path.startswith(prefix)
        and (
            (suffix is not None and path.endswith(suffix))
            or (filename is not None and PurePosixPath(path).name == filename)
        )
    ):
        path = ROOT / relpath
        if path.is_file():
            yield path


def _all_py_under_apps() -> list[Path]:
    out: list[Path] = []
    for p in _iter_files(APPS, suffix=".py"):
        if "__pycache__" in p.parts:
            continue
        out.append(p)
    return sorted(out)


def _all_app_packages() -> list[Path]:
    """Direct children of apps/ that contain apps.py (Django app roots)."""
    if not APPS.is_dir():
        return []
    tracked = _tracked_file_relpaths(ROOT)
    if tracked is not None:
        roots = []
        for relpath in sorted(tracked):
            parts = PurePosixPath(relpath).parts
            if len(parts) == 3 and parts[0] == "apps" and parts[2] == "apps.py":
                child = ROOT.joinpath(*parts[:2])
                if child.is_dir():
                    roots.append(child)
        return roots
    roots: list[Path] = []
    for child in sorted(APPS.iterdir()):
        if child.is_dir() and (child / "apps.py").is_file():
            roots.append(child)
    return roots


def _all_html_templates() -> list[Path]:
    if not TEMPLATES.is_dir():
        return []
    return sorted(_iter_files(TEMPLATES, suffix=".html"))


def _all_url_modules() -> list[Path]:
    if not APPS.is_dir():
        return []
    return sorted(_iter_files(APPS, filename="urls.py"))


def _all_marketplace_templates() -> list[Path]:
    mp_dir = TEMPLATES / "marketplace"
    if not mp_dir.is_dir():
        return []
    return sorted(_iter_files(mp_dir, suffix=".html"))


def _function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def _non_empty_code_lines(path: Path) -> int:
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    try:
        _configure_root(_resolve_base(parse_args(argv).base))
    except ValueError as exc:
        _fail(str(exc))
        return 1

    failures: list[str] = []

    app_roots = _all_app_packages()
    if not app_roots:
        _fail("no Django app packages under apps/")
        return 1

    py_files = _all_py_under_apps()
    if not py_files:
        _fail("no Python files under apps/")
        return 1

    html_files = _all_html_templates()
    if not html_files:
        _fail("no HTML templates under templates/")
        return 1

    url_modules = _all_url_modules()
    for um in url_modules:
        if "__pycache__" in um.parts:
            continue
        text = um.read_text(encoding="utf-8")
        if "urlpatterns" not in text:
            failures.append(f"{um.relative_to(ROOT)}: missing urlpatterns")

    # Routing glue (catalog lives on super + tenant urlconfs, not marketplace/urls.py).
    super_urls = ROOT / "apps/schools/super_urls.py"
    if not super_urls.is_file():
        failures.append("missing apps/schools/super_urls.py")
    else:
        s = super_urls.read_text(encoding="utf-8")
        if "app_catalog" not in s:
            failures.append("apps/schools/super_urls.py: missing app_catalog route hook")
        if "marketplace_views" not in s and "marketplace" not in s:
            failures.append("apps/schools/super_urls.py: missing marketplace view import")

    tenant_urls = ROOT / "config/tenant_urls.py"
    if not tenant_urls.is_file():
        failures.append("missing config/tenant_urls.py")
    else:
        t = tenant_urls.read_text(encoding="utf-8")
        if "tenant_app_catalog" not in t:
            failures.append("config/tenant_urls.py: missing tenant_app_catalog hook")

    # --- Ecosystem Python spine (AST) ---
    spine: list[tuple[str, frozenset[str]]] = [
        ("apps/marketplace/views.py", frozenset({"app_catalog", "tenant_app_catalog", "governance_console"})),
        ("apps/accounts/views_migration.py", frozenset({"migration_wizard", "migration_run_list"})),
        ("apps/accounts/views_district_interop.py", frozenset({"district_lms_interop"})),
        ("apps/siteconfig/views_package_rollback.py", frozenset({"tenant_installed_packages_rollback"})),
    ]
    for rel, required in spine:
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing {rel}")
            continue
        names = _function_names(path)
        missing = sorted(required - names)
        if missing:
            failures.append(f"{rel}: missing functions {missing}")

    engine = ROOT / "apps/packages/engine.py"
    if not engine.is_file():
        failures.append("missing apps/packages/engine.py")
    else:
        eng = engine.read_text(encoding="utf-8")
        # apply_stage is a persisted lifecycle field on InstalledPackage, not necessarily a method.
        for token in ("class PackageEngine", "apply_stage", "rollback"):
            if token not in eng:
                failures.append(f"apps/packages/engine.py: missing {token!r}")

    for rel, min_lines in (
        ("apps/marketplace/listing_display.py", 5),
        ("apps/marketplace/ecosystem_links.py", 5),
        ("apps/accounts/migration_services.py", 40),
    ):
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"missing {rel}")
            continue
        if _non_empty_code_lines(path) < min_lines:
            failures.append(f"{rel}: expected >= {min_lines} non-empty code lines")

    # --- Every marketplace template ---
    mp_dir = TEMPLATES / "marketplace"
    if not mp_dir.is_dir():
        failures.append("missing templates/marketplace/")
    else:
        m_templates = _all_marketplace_templates()
        if not m_templates:
            failures.append("no templates under templates/marketplace/")
        for tp in m_templates:
            try:
                body = tp.read_text(encoding="utf-8")
            except OSError as e:
                failures.append(f"{tp.relative_to(ROOT)}: read error {e}")
                continue
            if len(body.strip()) < 24:
                failures.append(f"{tp.relative_to(ROOT)}: template too small")
                continue
            if "{%" not in body and "<!DOCTYPE" not in body and "<html" not in body.lower():
                failures.append(
                    f"{tp.relative_to(ROOT)}: expected Django template markers or HTML root"
                )

    # --- Marketing spine files (beyond substring gate) ---
    for rel in (
        "templates/schools/marketing_landing.html",
        "templates/marketing/partials/live_flow_preview.html",
        "static/marketing/css/marketing-narrative-phase10.css",
    ):
        p = ROOT / rel
        if not p.is_file():
            failures.append(f"missing {rel}")
        elif _non_empty_code_lines(p) < 3:
            failures.append(f"{rel}: unexpectedly empty")

    if failures:
        for f in failures:
            _fail(f)
        return 1

    migration_py = sum(1 for p in py_files if "migrations" in p.parts)
    logic_py = len(py_files) - migration_py

    print(
        "OK   repo-wide ecosystem/marketing audit\n"
        f"     Django app packages: {len(app_roots)}\n"
        f"     apps/**/*.py: {len(py_files)} total ({logic_py} excluding migrations/, "
        f"{migration_py} under migrations/)\n"
        f"     templates/**/*.html: {len(html_files)}\n"
        f"     apps/**/urls.py modules: {len(url_modules)}\n"
        f"     templates/marketplace/**/*.html: "
        f"{len(_all_marketplace_templates())}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
