#!/usr/bin/env python3
"""Install RunMyCampus git hooks from the version-controlled ``.githooks/`` dir.

Right now this installs a single ``pre-push`` hook that runs the fast, deps-free
architectural-boundary gates (see ``scripts/pre_push_boundary_check.py``). It is
warn-only by default, so installing it never risks wedging a push; flip
``RMC_PREPUSH_STRICT=1`` when you want red gates to block.

Run once per clone (hooks are not themselves version-controlled — only the
templates in ``.githooks/`` are)::

    python scripts/install_git_hooks.py            # install / update
    python scripts/install_git_hooks.py --uninstall
    python scripts/install_git_hooks.py --check     # report status, exit 1 if missing

Idempotent: re-running refreshes the hook to the current template. An existing
hook we did not write is backed up to ``<name>.backup`` before being replaced.
"""

from __future__ import annotations

import argparse
import shutil
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = REPO_ROOT / ".githooks"
# Any installed hook carrying this marker is considered "ours" and safe to
# overwrite without a backup.
OURS_MARKER = "RMC-PRE-PUSH-HOOK-V1"
HOOK_NAMES = ("pre-push",)


def _hooks_dir() -> Path:
    """Effective hooks directory for this clone (honours core.hooksPath)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--git-path", "hooks"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fall back to the conventional location if git isn't callable.
        out = ".git/hooks"
    path = Path(out)
    if not path.is_absolute():
        path = (REPO_ROOT / path).resolve()
    return path


def _is_ours(path: Path) -> bool:
    try:
        return OURS_MARKER in path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def _make_executable(path: Path) -> None:
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def install() -> int:
    hooks_dir = _hooks_dir()
    hooks_dir.mkdir(parents=True, exist_ok=True)
    changed = 0
    for name in HOOK_NAMES:
        template = TEMPLATE_DIR / name
        if not template.is_file():
            print(f"  ! template missing: {template}", file=sys.stderr)
            continue
        target = hooks_dir / name
        template_body = template.read_text(encoding="utf-8")
        if target.exists():
            if target.read_text(encoding="utf-8", errors="ignore") == template_body:
                print(f"  = {name}: already current")
                continue
            if not _is_ours(target):
                backup = target.with_suffix(target.suffix + ".backup")
                shutil.copy2(target, backup)
                print(f"  ~ {name}: backed up existing hook -> {backup.name}")
        target.write_text(template_body, encoding="utf-8", newline="\n")
        _make_executable(target)
        print(f"  + {name}: installed -> {target}")
        changed += 1
    if changed:
        print("Done. pre-push runs in WARN mode; set RMC_PREPUSH_STRICT=1 to block red pushes.")
    else:
        print("Nothing to do; hooks already current.")
    return 0


def uninstall() -> int:
    hooks_dir = _hooks_dir()
    for name in HOOK_NAMES:
        target = hooks_dir / name
        if target.exists() and _is_ours(target):
            target.unlink()
            print(f"  - {name}: removed")
            backup = target.with_suffix(target.suffix + ".backup")
            if backup.exists():
                shutil.move(str(backup), str(target))
                print(f"  ~ {name}: restored prior hook from {backup.name}")
        else:
            print(f"  = {name}: not ours / absent, left untouched")
    return 0


def check() -> int:
    hooks_dir = _hooks_dir()
    missing = 0
    for name in HOOK_NAMES:
        target = hooks_dir / name
        if target.exists() and _is_ours(target):
            print(f"  ok {name}: installed at {target}")
        else:
            print(f"  MISSING {name}: run `python scripts/install_git_hooks.py`")
            missing += 1
    return 1 if missing else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--uninstall", action="store_true", help="Remove installed hooks.")
    group.add_argument("--check", action="store_true", help="Report status; exit 1 if missing.")
    args = parser.parse_args(argv)
    if args.uninstall:
        return uninstall()
    if args.check:
        return check()
    return install()


if __name__ == "__main__":
    raise SystemExit(main())
