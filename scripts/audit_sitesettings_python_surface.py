#!/usr/bin/env python3
"""
Granular SiteSettings / runtime-settings surface audit over ``apps/**/*.py`` (non-migration, non-test).

**1035+:** Enforces a single class-level access story: only
``apps/siteconfig/models.py`` and ``apps/platform_runtime/helpers.py`` may import or
reference the ``SiteSettings`` ORM class directly (``SiteSettings.objects``,
``from apps.siteconfig.models import SiteSettings``, ``get_model('siteconfig','SiteSettings')``,
``SiteSettings.get_solo``). Other code must use
``get_effective_site_settings`` / ``get_platform_site_settings_record`` (see
``apps/platform_runtime/site_settings_read_access``).

Classifies high-gravity patterns for Phase B dismantling. Writes
``docs/generated/sitesettings_python_surface_audit.json`` (``schema_version`` 2+).

Excludes: */migrations/*, */tests/*, ``test_*.py``, ``__pycache__``.

Exit code **1** if any violation is reported.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "generated" / "sitesettings_python_surface_audit.json"

SCHEMA_VERSION = 2

# Same structural rule as ``lint_sitesettings_orm_singleton`` / SITESETTINGS doc.
CLASS_LEVEL_ALLOWLIST = frozenset(
    {
        "apps/siteconfig/models.py",
        "apps/platform_runtime/helpers.py",
    }
)

SKIP_DIR_PARTS = frozenset({"migrations", "tests", "__pycache__"})

RE_IMPORT_SITESETTINGS_PAREN = re.compile(
    r"from\s+apps\.siteconfig\.models\s+import\s*\([^)]*\bSiteSettings\b",
    re.DOTALL,
)
RE_IMPORT_LINE = re.compile(
    r"from\s+apps\.siteconfig\.models\s+import\s+[^\n#;]*\bSiteSettings\b",
)
RE_GET_MODEL_SS = re.compile(
    r"(?:apps\.)?get_model\s*\(\s*['\"]siteconfig['\"]\s*,\s*['\"]SiteSettings['\"]\s*\)",
)
RE_GET_SOLO = re.compile(r"\bSiteSettings\.get_solo\s*\(")
RE_LOAD = re.compile(r"\bSiteSettings\.load\s*\(")


def _iter_product_py_files(apps_root: Path):
    for path in apps_root.rglob("*.py"):
        if SKIP_DIR_PARTS.intersection(path.parts):
            continue
        name = path.name
        if name.startswith("test_") or name.endswith("_tests.py"):
            continue
        rel = path.relative_to(REPO)
        srel = rel.as_posix()
        if "/tests/" in srel:
            continue
        yield path, srel


def scan_file_text(text: str) -> dict[str, int]:
    """Return pattern counts for one file (used by audit + unit tests)."""
    rd_singleton = len(re.findall(r"RuntimeDefaults\.get_singleton\s*\(\s*\)", text))
    im = 1 if RE_IMPORT_LINE.search(text) or RE_IMPORT_SITESETTINGS_PAREN.search(text) else 0
    return {
        "sitesettings_word": len(re.findall(r"\bSiteSettings\b", text)),
        "get_solo_paren": text.count("get_solo("),
        "sitesettings_objects": text.count("SiteSettings.objects"),
        "import_siteconfig_sitesettings": im,
        "django_get_model_sitesettings": len(RE_GET_MODEL_SS.findall(text)),
        "sitesettings_get_solo": len(RE_GET_SOLO.findall(text)),
        "sitesettings_load": len(RE_LOAD.findall(text)),
        "get_effective_site_settings": text.count("get_effective_site_settings("),
        "get_platform_site_settings_record": text.count(
            "get_platform_site_settings_record("
        ),
        "runtime_defaults_get_singleton": rd_singleton,
    }


def _violations_for_path(srel: str, m: dict[str, int | bool]) -> list[dict[str, str]]:
    if srel in CLASS_LEVEL_ALLOWLIST:
        return []
    out: list[dict[str, str]] = []
    if m.get("sitesettings_objects", 0) and int(m["sitesettings_objects"]) > 0:
        out.append(
            {
                "kind": "SiteSettings.objects",
                "path": srel,
                "detail": str(m["sitesettings_objects"]),
            }
        )
    if m.get("import_siteconfig_sitesettings"):
        out.append(
            {
                "kind": "import SiteSettings from apps.siteconfig.models",
                "path": srel,
                "detail": "1",
            }
        )
    gmc = int(m.get("django_get_model_sitesettings", 0) or 0)
    if gmc > 0:
        out.append(
            {
                "kind": "get_model('siteconfig','SiteSettings')",
                "path": srel,
                "detail": str(gmc),
            }
        )
    gs = int(m.get("sitesettings_get_solo", 0) or 0)
    if gs > 0:
        out.append(
            {
                "kind": "SiteSettings.get_solo(",
                "path": srel,
                "detail": str(gs),
            }
        )
    ld = int(m.get("sitesettings_load", 0) or 0)
    if ld > 0:
        out.append(
            {
                "kind": "SiteSettings.load(",
                "path": srel,
                "detail": str(ld),
            }
        )
    return out


def _metric_keys() -> tuple[str, ...]:
    return (
        "sitesettings_word",
        "get_solo_paren",
        "sitesettings_objects",
        "import_siteconfig_sitesettings",
        "django_get_model_sitesettings",
        "sitesettings_get_solo",
        "sitesettings_load",
        "get_effective_site_settings",
        "get_platform_site_settings_record",
        "runtime_defaults_get_singleton",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stdout-json",
        action="store_true",
        help="Print full JSON to stdout",
    )
    args = parser.parse_args(argv)

    apps_root = REPO / "apps"
    if not apps_root.is_dir():
        print("audit_sitesettings_python_surface: FAIL — apps/ missing", file=sys.stderr)
        return 1

    by_app: dict[str, dict[str, int]] = defaultdict(
        lambda: defaultdict(int)  # type: ignore[assignment]
    )
    per_file: list[dict] = []
    all_violations: list[dict[str, str]] = []

    for path, srel in _iter_product_py_files(apps_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = scan_file_text(text)

        if not any(m.values()):
            continue
        app = srel.split("/")[1] if srel.startswith("apps/") else "unknown"
        by_app[app]["files"] += 1
        for k, v in m.items():
            by_app[app][k] += v
        row = {"relpath": srel, **m}
        per_file.append(row)
        for v in _violations_for_path(srel, m):
            all_violations.append(v)

    keys = _metric_keys()
    totals: dict[str, int] = defaultdict(int)
    totals["files_with_any_hit"] = len(per_file)
    for pf in per_file:
        for k in keys:
            totals[k] += pf.get(k, 0)

    per_file_sorted = sorted(per_file, key=lambda x: x.get("relpath", ""))
    top_read_path = sorted(
        per_file,
        key=lambda x: x.get("get_effective_site_settings", 0),
        reverse=True,
    )[:30]
    top_word = sorted(
        per_file, key=lambda x: x.get("sitesettings_word", 0), reverse=True
    )[:30]

    by_kind: dict[str, int] = defaultdict(int)
    for v in all_violations:
        by_kind[v["kind"]] += 1

    # Back-compat keys for 1033 consumers
    objects_only = [x for x in all_violations if x["kind"] == "SiteSettings.objects"]

    payload = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "class_level_allowlist": sorted(CLASS_LEVEL_ALLOWLIST),
        "totals": {**{k: int(totals[k]) for k in keys}, "files_with_any_hit": len(per_file)},
        "by_app": {
            k: {kk: int(vv) for kk, vv in sorted(v.items())}
            for k, v in sorted(by_app.items())
        },
        "per_file": per_file_sorted,
        "by_kind": dict(sorted(by_kind.items())),
        "high_gravity_read_paths": top_read_path,
        "top_files_by_sitesettings_word": top_word,
        "violations": all_violations,
        "sitesettings_objects_violations": objects_only,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if args.stdout_json:
        print(json.dumps(payload, indent=2))
    else:
        print("audit_sitesettings_python_surface: OK" if not all_violations else "audit_sitesettings_python_surface: VIOLATIONS")
        print(f"  files_with_any_hit: {len(per_file)}")
        print(f"  total violations: {len(all_violations)}")
        print(f"  get_effective_site_settings( total calls: {totals['get_effective_site_settings']}")
        if all_violations:
            for v in all_violations[:20]:
                print(f"  - {v['path']}: {v['kind']} ({v.get('detail','')})")
            if len(all_violations) > 20:
                print(f"  ... and {len(all_violations) - 20} more")
        print(f"  written: {OUT.as_posix()}")

    return 1 if all_violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
