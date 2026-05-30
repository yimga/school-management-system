#!/usr/bin/env python3
"""
World Engine §11 i18n CI gate — catalog freshness + polib compile path.

Enforces:
  1. locale/en/LC_MESSAGES/django.po covers all scanned translatable strings
  2. sync_i18n_catalog --dry-run adds zero new msgids (committed .po is current)
  3. sync_i18n_catalog --compile succeeds (polib .mo path; no GNU gettext required)

When GNU gettext is available, also runs compilemessages for en as a secondary check.

Fix drift: python manage.py sync_i18n_catalog --compile
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str], *, label: str) -> int:
    print(f"--- {label} ---", flush=True)
    proc = subprocess.run(cmd, cwd=ROOT)
    if proc.returncode != 0:
        print(f"verify_world_engine_i18n_ci: FAIL at {label}", file=sys.stderr)
        return proc.returncode
    print(f"OK: {label}\n", flush=True)
    return 0


def _configure_django() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()


def _dry_run_has_new_msgids() -> tuple[bool, dict[str, int]]:
    from django.conf import settings

    from apps.siteconfig.i18n_catalog_builder import run_sync

    langs = list(settings.LANGUAGES)
    _discovered, added, _pruned = run_sync(
        base_dir=settings.BASE_DIR,
        languages=langs,
        dry_run=True,
        compile_mo=False,
        prune_stale=False,
    )
    return any(n > 0 for n in added.values()), added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="World Engine i18n CI verifier")
    parser.add_argument("--base", default=str(ROOT), help="Repository root")
    parser.add_argument(
        "--skip-compile",
        action="store_true",
        help="Skip sync_i18n_catalog --compile (catalog freshness only)",
    )
    args = parser.parse_args(argv)

    base = Path(args.base).resolve()
    py = sys.executable

    po_path = base / "locale" / "en" / "LC_MESSAGES" / "django.po"
    if not po_path.is_file():
        print(f"verify_world_engine_i18n_ci: missing {po_path}", file=sys.stderr)
        return 1

    code = _run(
        [py, str(base / "scripts" / "verify_i18n_catalog_fresh.py"), "--base", str(base)],
        label="verify_i18n_catalog_fresh",
    )
    if code:
        return code

    if str(base) not in sys.path:
        sys.path.insert(0, str(base))
    _configure_django()

    has_new, added = _dry_run_has_new_msgids()
    if has_new:
        print(
            "verify_world_engine_i18n_ci: FAIL — django.po is stale vs codebase scan",
            file=sys.stderr,
        )
        for code_lang, count in sorted(added.items()):
            if count:
                print(f"  {code_lang}: +{count} new msgids", file=sys.stderr)
        print("Fix: python manage.py sync_i18n_catalog --compile", file=sys.stderr)
        return 1
    print("OK: sync_i18n_catalog dry-run — no new msgids\n", flush=True)

    if not args.skip_compile:
        code = _run(
            [py, str(base / "manage.py"), "sync_i18n_catalog", "--compile"],
            label="sync_i18n_catalog --compile",
        )
        if code:
            return code

        mo_path = base / "locale" / "en" / "LC_MESSAGES" / "django.mo"
        if not mo_path.is_file():
            print(f"verify_world_engine_i18n_ci: missing {mo_path} after compile", file=sys.stderr)
            return 1

        if shutil.which("msgfmt"):
            code = _run(
                [py, str(base / "manage.py"), "compilemessages", "-l", "en"],
                label="compilemessages -l en (gettext)",
            )
            if code:
                return code

    print("verify_world_engine_i18n_ci: WORLD_ENGINE_I18N_CI_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
