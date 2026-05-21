#!/usr/bin/env python3
"""
Scan apps/**, templates/**, services/**, tests/** for SiteSettings-related symbols.

Writes docs/generated/sitesettings_dependency_map.json for modular config migration.
Run from repo root: python scripts/generate_sitesettings_dependency_map.py
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "sitesettings_dependency_map.json"

SCAN_ROOTS = ("apps", "templates", "services", "tests", "emis")

# Patterns: (kind, regex)
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("SiteSettings_word", re.compile(r"\bSiteSettings\b")),
    ("SiteSettings_objects", re.compile(r"\bSiteSettings\.objects\b")),
    ("SiteSettings_get_solo", re.compile(r"\bSiteSettings\.get_solo\b")),
    ("SiteSettings_load", re.compile(r"\bSiteSettings\.load\b")),
    ("get_model_SiteSettings", re.compile(
        r"get_model\s*\(\s*['\"]siteconfig['\"]\s*,\s*['\"]SiteSettings['\"]"
    )),
    ("import_SiteSettings_models", re.compile(
        r"from\s+apps\.siteconfig\.models\s+import\s+[^\n;#]*\bSiteSettings\b"
    )),
    ("get_effective_site_settings", re.compile(r"\bget_effective_site_settings\s*\(")),
    ("get_platform_site_settings_record", re.compile(
        r"\bget_platform_site_settings_record\s*\(",
    )),
    ("get_sitesettings", re.compile(r"\bget_sitesettings\s*\(")),
    ("site_settings_read_access", re.compile(
        r"apps\.platform_runtime\.site_settings_read_access",
    )),
    ("config_service_facade", re.compile(
        r"apps\.siteconfig\.config_service",
    )),
    ("chained_effective_attribute_read", re.compile(
        r"get_effective_site_settings\s*\([^)]*\)[^\n]{0,120}?[\.\[]",
    )),
]

TEMPLATE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("template_site_settings_identifier", re.compile(r"\bsite_settings\b")),
    ("template_SiteSettings_comment", re.compile(r"SiteSettings")),
]


def _should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if "__pycache__" in parts:
        return True
    if path.suffix not in {".py", ".html", ".htm"}:
        return True
    return False


def _scan_file(path: Path, rel: str) -> list[dict[str, object]]:
    hits: list[dict[str, object]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return hits
    lines = text.splitlines()
    patterns = TEMPLATE_PATTERNS if path.suffix in {".html", ".htm"} else PATTERNS
    for i, line in enumerate(lines, start=1):
        if path.suffix == ".py" and line.strip().startswith("#"):
            continue
        for kind, rx in patterns:
            if rx.search(line):
                stripped = line.strip()
                if len(stripped) > 240:
                    stripped = stripped[:237] + "..."
                hits.append(
                    {
                        "line": i,
                        "kind": kind,
                        "snippet": stripped,
                    }
                )
    return hits


def main() -> int:
    by_file: dict[str, list[dict[str, object]]] = {}
    summary: dict[str, int] = defaultdict(int)

    for root_name in SCAN_ROOTS:
        base = ROOT / root_name
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file() and not _should_skip(path):
                rel = path.relative_to(ROOT).as_posix()
                hits = _scan_file(path, rel)
                if hits:
                    by_file[rel] = hits
                    for h in hits:
                        summary[str(h["kind"])] += 1

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "canonical_read_facade": "apps/siteconfig/config_service.py",
        "scan_roots": list(SCAN_ROOTS),
        "synonyms_documented": {
            "get_sitesettings": (
                "No symbol get_sitesettings() in tree; use get_effective_site_settings / "
                "get_platform_site_settings_record."
            ),
        },
        "summary_counts_by_kind": dict(sorted(summary.items())),
        "files_with_hits": len(by_file),
        "hits_by_file": dict(sorted(by_file.items())),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(by_file)} files, {sum(summary.values())} hits)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
