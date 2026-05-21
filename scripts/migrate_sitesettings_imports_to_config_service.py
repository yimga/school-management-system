#!/usr/bin/env python3
"""
Replace ``from apps.platform_runtime.site_settings_read_access import`` with
``from apps.siteconfig.config_service import`` for application code.

Skips: migrations, tests, helpers.py, site_settings_read_access.py,
platform_runtime except runtime_resolver.py.

Run from repo root:
  python scripts/migrate_sitesettings_imports_to_config_service.py
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APPS = REPO / "apps"

OLD_PREFIX = "from apps.platform_runtime.site_settings_read_access import"
NEW_PREFIX = "from apps.siteconfig.config_service import"

SKIP_DIR_PARTS = frozenset({"migrations", "tests", "__pycache__"})


def skip_file(path: Path) -> bool:
    name = path.name
    if not name.endswith(".py"):
        return True
    if name.startswith("test_") or name.endswith("_tests.py"):
        return True
    if SKIP_DIR_PARTS.intersection(path.parts):
        return True
    if name in {"helpers.py", "site_settings_read_access.py"}:
        return True
    if "platform_runtime" in path.parts:
        return path.name != "runtime_resolver.py"
    return False


def main() -> int:
    changed: list[Path] = []
    for path in APPS.rglob("*.py"):
        if skip_file(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if OLD_PREFIX not in text:
            continue
        new_text = text.replace(OLD_PREFIX, NEW_PREFIX)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
            changed.append(path)

    for p in sorted(changed, key=lambda x: str(x)):
        print(p.relative_to(REPO))
    print(f"migrate_sitesettings_imports_to_config_service: updated {len(changed)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
