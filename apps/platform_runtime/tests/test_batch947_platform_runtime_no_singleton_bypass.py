"""
§11.4 batch 947 / PATH §6.2 III.4 + III.6 — platform_runtime must not reintroduce
SiteSettings singleton bypasses (get_solo / load / direct SiteSettings.objects).

Complements repo-wide ``lint_sitesettings_orm_singleton.py`` with an app-local guard
so regressions in ``apps/platform_runtime/`` fail in a focused test.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from apps.platform_runtime.tests.support.paths import repo_root

_SKIP_DIR_PARTS = frozenset({"tests", "migrations", "__pycache__", "management"})

_GET_SOLO_RE = re.compile(r"SiteSettings\.get_solo\s*\(")
_LOAD_RE = re.compile(r"SiteSettings\.load\s*\(")
_OBJECTS_RE = re.compile(r"SiteSettings\.objects\.\w+\s*\(")

# Only helpers may touch the slim row via ORM; it uses ``_TenantSettingsModel``, not
# the ``SiteSettings`` class name, for queryset entrypoints.
_HELPERS_SUFFIX = Path("apps/platform_runtime/helpers.py")


def _iter_platform_runtime_py_files(root: Path):
    app_root = root / "apps" / "platform_runtime"
    if not app_root.is_dir():
        return
    for path in app_root.rglob("*.py"):
        rel = path.relative_to(root)
        parts = set(rel.parts)
        if parts & _SKIP_DIR_PARTS:
            continue
        yield rel, path


class PlatformRuntimeNoSingletonBypassTests(unittest.TestCase):
    def test_no_get_solo_load_or_sitesettings_objects_outside_helpers(self):
        root = repo_root()
        bad: list[str] = []
        for rel, path in _iter_platform_runtime_py_files(root):
            if rel == _HELPERS_SUFFIX:
                text = path.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(text.splitlines(), 1):
                    head = line.split("#", 1)[0].strip()
                    if not head:
                        continue
                    if _GET_SOLO_RE.search(head) or _LOAD_RE.search(head):
                        bad.append(f"{rel.as_posix()}:{i}: {head[:100]}")
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for i, line in enumerate(text.splitlines(), 1):
                head = line.split("#", 1)[0].strip()
                if not head:
                    continue
                if (
                    _GET_SOLO_RE.search(head)
                    or _LOAD_RE.search(head)
                    or _OBJECTS_RE.search(head)
                ):
                    bad.append(f"{rel.as_posix()}:{i}: {head[:100]}")
        self.assertFalse(
            bad,
            "platform_runtime must use get_effective_site_settings / "
            "get_platform_site_settings_record, not SiteSettings singleton shortcuts:\n"
            + "\n".join(bad),
        )
