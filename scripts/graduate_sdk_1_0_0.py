#!/usr/bin/env python3
"""Wave 9 Agent N (v3.58.x) — SDK 1.0.0 graduation script.

Bumps both webhook-verifier SDK packages from ``1.0.0-rc.1`` to
``1.0.0`` and adds CHANGELOG entries. Dry-run by default; ``--apply``
performs the writes.

Refuses to run before **2026-08-17** (the 90-day field-test window
opened 2026-05-19 per v3.38.0). To override (e.g. emergency early
graduation forced by a critical bug), set the env var
``RMC_SDK_GRADUATION_OVERRIDE_DATE_CHECK=1``. The override is logged
to stderr.

Touched files (per package):

  Python (``packages/runmycampus-webhook-verifier-py/``):
    * ``pyproject.toml`` — ``version = "1.0.0-rc.1"`` → ``"1.0.0"``
    * ``src/runmycampus_webhook_verifier/__init__.py`` —
      ``__version__ = "1.0.0-rc.1"`` → ``"1.0.0"``
    * ``CHANGELOG.md`` — prepend a new ``## [1.0.0] — <date>`` entry
      under the existing ``# Changelog`` heading.

  JS (``packages/runmycampus-webhook-verifier-js/``):
    * ``package.json`` — ``"version": "1.0.0-rc.1"`` → ``"1.0.0"``
    * ``src/index.ts`` — ``export const VERSION = "1.0.0-rc.1"`` → ``"1.0.0"``
    * ``CHANGELOG.md`` — same prepend pattern.

Exit codes:

  * 0 — dry-run or apply succeeded.
  * 1 — date-window refusal (no override).
  * 2 — file IO error or unexpected state (already graduated, missing
    file, version string not found).

Stdlib-only. No third-party deps.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import io
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parent.parent
PACKAGES_DIR = REPO_ROOT / "packages"

PY_PACKAGE_DIR = PACKAGES_DIR / "runmycampus-webhook-verifier-py"
JS_PACKAGE_DIR = PACKAGES_DIR / "runmycampus-webhook-verifier-js"

CURRENT_VERSION = "1.0.0-rc.1"
TARGET_VERSION = "1.0.0"

GRADUATION_WINDOW_OPENS = _dt.date(2026, 8, 17)
OVERRIDE_ENV = "RMC_SDK_GRADUATION_OVERRIDE_DATE_CHECK"


class GraduationError(RuntimeError):
    """Wraps any unexpected state during the graduation walk."""


# ─── change planning ─────────────────────────────────────────────────────


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except OSError as exc:
        raise GraduationError(
            f"could not read {p}: {type(exc).__name__}",
        ) from exc


def _write(p: Path, content: str) -> None:
    try:
        p.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise GraduationError(
            f"could not write {p}: {type(exc).__name__}",
        ) from exc


def _expect_substring(content: str, needle: str, where: Path) -> None:
    """Raise if ``needle`` doesn't appear in ``content``."""
    if needle not in content:
        raise GraduationError(
            f"{where}: expected substring {needle!r} not found "
            "(maybe already graduated, or version string in unexpected shape)."
        )


def _plan_py_pyproject() -> tuple[Path, str, str, str]:
    """Return (path, new_content, change_description, original_content)."""
    p = PY_PACKAGE_DIR / "pyproject.toml"
    src = _read(p)
    needle = f'version = "{CURRENT_VERSION}"'
    _expect_substring(src, needle, p)
    new = src.replace(needle, f'version = "{TARGET_VERSION}"', 1)
    return p, new, f'{p.name}: version "{CURRENT_VERSION}" -> "{TARGET_VERSION}"', src


def _plan_py_init() -> tuple[Path, str, str, str]:
    p = PY_PACKAGE_DIR / "src" / "runmycampus_webhook_verifier" / "__init__.py"
    src = _read(p)
    needle = f'__version__ = "{CURRENT_VERSION}"'
    _expect_substring(src, needle, p)
    new = src.replace(needle, f'__version__ = "{TARGET_VERSION}"', 1)
    return p, new, f'{p.name}: __version__ "{CURRENT_VERSION}" -> "{TARGET_VERSION}"', src


def _plan_py_changelog(today: _dt.date) -> tuple[Path, str, str, str]:
    p = PY_PACKAGE_DIR / "CHANGELOG.md"
    src = _read(p)
    # Idempotency guard — refuse if already graduated.
    if f"## [{TARGET_VERSION}] —" in src:
        raise GraduationError(
            f"{p}: appears already graduated (entry for "
            f"[{TARGET_VERSION}] already present)."
        )
    entry = _changelog_entry(TARGET_VERSION, today, package_kind="python")
    # Insert AFTER the file's intro paragraph (which ends just before
    # the first existing version heading).
    marker = "## ["
    idx = src.find(marker)
    if idx < 0:
        raise GraduationError(
            f"{p}: could not find a '## [' heading to anchor insertion."
        )
    new = src[:idx] + entry + "\n\n" + src[idx:]
    return p, new, f'{p.name}: prepend [{TARGET_VERSION}] entry', src


def _plan_js_package_json() -> tuple[Path, str, str, str]:
    p = JS_PACKAGE_DIR / "package.json"
    src = _read(p)
    needle = f'"version": "{CURRENT_VERSION}"'
    _expect_substring(src, needle, p)
    new = src.replace(needle, f'"version": "{TARGET_VERSION}"', 1)
    # Verify JSON still parses.
    try:
        json.loads(new)
    except ValueError as exc:
        raise GraduationError(
            f"{p}: post-bump JSON does not parse: {exc}"
        ) from exc
    return p, new, f'{p.name}: version "{CURRENT_VERSION}" -> "{TARGET_VERSION}"', src


def _plan_js_index_ts() -> tuple[Path, str, str, str]:
    p = JS_PACKAGE_DIR / "src" / "index.ts"
    src = _read(p)
    needle = f'export const VERSION = "{CURRENT_VERSION}"'
    _expect_substring(src, needle, p)
    new = src.replace(
        needle, f'export const VERSION = "{TARGET_VERSION}"', 1,
    )
    return p, new, f'{p.name}: VERSION "{CURRENT_VERSION}" -> "{TARGET_VERSION}"', src


def _plan_js_changelog(today: _dt.date) -> tuple[Path, str, str, str]:
    p = JS_PACKAGE_DIR / "CHANGELOG.md"
    src = _read(p)
    if f"## [{TARGET_VERSION}] —" in src:
        raise GraduationError(
            f"{p}: appears already graduated (entry for "
            f"[{TARGET_VERSION}] already present)."
        )
    entry = _changelog_entry(TARGET_VERSION, today, package_kind="js")
    marker = "## ["
    idx = src.find(marker)
    if idx < 0:
        raise GraduationError(
            f"{p}: could not find a '## [' heading to anchor insertion."
        )
    new = src[:idx] + entry + "\n\n" + src[idx:]
    return p, new, f'{p.name}: prepend [{TARGET_VERSION}] entry', src


def _changelog_entry(version: str, today: _dt.date, *, package_kind: str) -> str:
    """Return the Keep-a-Changelog-formatted entry."""
    iso = today.isoformat()
    pkg_label = "PyPI" if package_kind == "python" else "npm"
    body = (
        f"## [{version}] — {iso}\n"
        f"\n"
        f"Graduation from `{CURRENT_VERSION}` to `{version}`. The public "
        f"API surface listed in `STABILITY.md` is now frozen ({pkg_label}); "
        f"breaking changes require a 2.0 major bump.\n"
        f"\n"
        f"### Changed\n"
        f"\n"
        f"- Version bumped from `{CURRENT_VERSION}` to `{version}` after "
        f"completion of the 90-day field-test window opened 2026-05-19.\n"
        f"- No public-API surface changes; all `1.0.0-rc.1` callers continue "
        f"to work unmodified.\n"
        f"\n"
        f"### Notes\n"
        f"\n"
        f"- `LEGACY_HEADER_DEPRECATION_DATE = 2026-08-18` remains the canonical "
        f"sunset for the legacy header family.\n"
        f"- See `docs/SDK_1_0_0_GRADUATION_RUNBOOK.md` for the operator graduation "
        f"procedure."
    )
    return body


def _plan_all(today: _dt.date) -> list[tuple[Path, str, str, str]]:
    """Return the full list of (path, new_content, description, original)."""
    return [
        _plan_py_pyproject(),
        _plan_py_init(),
        _plan_py_changelog(today),
        _plan_js_package_json(),
        _plan_js_index_ts(),
        _plan_js_changelog(today),
    ]


# ─── date-window guard ──────────────────────────────────────────────────


def _date_window_ok(today: _dt.date) -> tuple[bool, str]:
    """Return ``(ok, reason)``. ok=True when today >= 2026-08-17 OR override."""
    if today >= GRADUATION_WINDOW_OPENS:
        return True, f"graduation window opened {GRADUATION_WINDOW_OPENS.isoformat()}"
    if os.environ.get(OVERRIDE_ENV, "") == "1":
        return True, (
            f"date check overridden via {OVERRIDE_ENV}=1 "
            f"(today={today.isoformat()}, window opens "
            f"{GRADUATION_WINDOW_OPENS.isoformat()})"
        )
    return False, (
        f"refused — today={today.isoformat()} is before "
        f"{GRADUATION_WINDOW_OPENS.isoformat()}; set {OVERRIDE_ENV}=1 "
        "to override for emergency early graduation."
    )


# ─── main ────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Graduate webhook-verifier SDK from 1.0.0-rc.1 to 1.0.0.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Without this flag, the script runs in dry-run mode.",
    )
    parser.add_argument(
        "--today",
        type=str,
        default="",
        help=(
            "Override today's date as ISO YYYY-MM-DD (testing only). "
            "Default: current local date."
        ),
    )
    args = parser.parse_args(argv)

    today = _dt.date.today()
    if args.today:
        try:
            today = _dt.date.fromisoformat(args.today)
        except ValueError as exc:
            sys.stderr.write(f"--today not parseable as ISO date: {exc}\n")
            return 2

    ok, reason = _date_window_ok(today)
    if not ok:
        sys.stderr.write(f"graduate_sdk_1_0_0: {reason}\n")
        return 1
    sys.stderr.write(f"graduate_sdk_1_0_0: date check {reason}\n")

    try:
        plans = _plan_all(today)
    except GraduationError as exc:
        sys.stderr.write(f"graduate_sdk_1_0_0: {exc}\n")
        return 2

    sys.stdout.write(
        f"graduate_sdk_1_0_0: planned {len(plans)} edits "
        f"(target_version={TARGET_VERSION}):\n"
    )
    for path, _new, desc, _orig in plans:
        sys.stdout.write(f"  - {desc}\n")

    if not args.apply:
        sys.stdout.write(
            "graduate_sdk_1_0_0: DRY-RUN — pass --apply to write changes.\n"
        )
        return 0

    # Apply each edit. We perform them sequentially; if any single
    # write fails the script returns 2 and the operator must manually
    # `git restore` the partial edits.
    applied: list[Path] = []
    for path, new_content, desc, _orig in plans:
        try:
            _write(path, new_content)
            applied.append(path)
            sys.stdout.write(f"graduate_sdk_1_0_0: applied {desc}\n")
        except GraduationError as exc:
            sys.stderr.write(
                f"graduate_sdk_1_0_0: APPLY FAILED at {desc}: {exc}\n"
                f"  applied so far: {[str(p) for p in applied]}\n"
                "  manual git restore may be required.\n"
            )
            return 2

    sys.stdout.write(
        f"graduate_sdk_1_0_0: APPLIED {len(applied)} edits. "
        "Next: tag both packages (webhook-verifier-py-v1.0.0 + "
        "webhook-verifier-js-v1.0.0) and push tags to trigger "
        "the release workflows.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
