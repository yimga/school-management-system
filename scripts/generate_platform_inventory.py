#!/usr/bin/env python3
"""
Generate the platform inventory required for the north-star hard-freeze phase.

Outputs:
- docs/generated/platform_inventory.json
- docs/generated/platform_inventory.md

Use `--write` to refresh committed artifacts and `--check` to fail CI when the
artifacts are stale.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs" / "generated"
JSON_PATH = DOCS_DIR / "platform_inventory.json"
MD_PATH = DOCS_DIR / "platform_inventory.md"

sys.path.insert(0, str(ROOT))

from apps.siteconfig.domain_ownership import classify_site_settings_field  # noqa: E402

SITE_SETTINGS_START = re.compile(r"^class SiteSettings\(models\.Model\):")
SITE_SETTINGS_END = re.compile(r"^class ThemePack\(models\.Model\):")
FIELD_PATTERN = re.compile(r"^\s{4}([A-Za-z_][A-Za-z0-9_]*)\s*=\s*models\.")
SETTINGS_APP_PATTERN = re.compile(r"\"apps\.([a-z0-9_]+)(?:\.apps\.[A-Za-z0-9_]+)?\"")
COUNT_PATTERNS = {
    "except_exception": re.compile(r"\bexcept Exception\b"),
    "get_solo": re.compile(r"\bget_solo\s*\("),
    "site_settings": re.compile(r"\bSiteSettings\b"),
    "csrf_exempt": re.compile(r"\bcsrf_exempt\b"),
    "allow_any": re.compile(r"\bAllowAny\b"),
    "cursor_execute": re.compile(r"\bcursor\.execute\s*\("),
    "print_calls": re.compile(r"\bprint\s*\("),
    "gilead": re.compile(r"gilead", re.IGNORECASE),
}
SKIP_PARTS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}


def _iter_files(*suffixes: str):
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if suffixes and path.suffix.lower() not in suffixes:
            continue
        yield path


def _safe_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _site_settings_fields() -> list[dict[str, str]]:
    models_path = ROOT / "apps" / "siteconfig" / "models.py"
    in_block = False
    fields: list[dict[str, str]] = []
    for line in _safe_text(models_path).splitlines():
        if SITE_SETTINGS_START.match(line):
            in_block = True
            continue
        if in_block and SITE_SETTINGS_END.match(line):
            break
        if not in_block:
            continue
        match = FIELD_PATTERN.match(line)
        if not match:
            continue
        field_name = match.group(1)
        fields.append(
            {
                "field_name": field_name,
                "owner": classify_site_settings_field(field_name),
            }
        )
    return fields


def _baseline_counts() -> dict[str, int]:
    counters = Counter()
    py_files = list(_iter_files(".py"))
    counters["python_files"] = len(py_files)
    counters["html_files"] = sum(1 for _ in _iter_files(".html"))
    counters["markdown_files"] = sum(1 for _ in _iter_files(".md"))
    counters["migration_files"] = sum(1 for path in py_files if "migrations" in path.parts)
    counters["management_commands"] = sum(
        1
        for path in py_files
        if "management" in path.parts and "commands" in path.parts and path.name != "__init__.py"
    )
    gilead_files = set()
    file_pool = py_files + list(_iter_files(".html", ".md", ".json", ".yaml", ".yml", ".sh", ".ps1"))
    for path in file_pool:
        text = _safe_text(path)
        for key, pattern in COUNT_PATTERNS.items():
            hits = pattern.findall(text)
            if hits:
                counters[key] += len(hits)
                if key == "gilead":
                    gilead_files.add(path.relative_to(ROOT).as_posix())
    counters["gilead_files"] = len(gilead_files)
    return dict(counters)


def _largest_python_files(limit: int = 12) -> list[dict[str, int | str]]:
    files = sorted(_iter_files(".py"), key=lambda path: path.stat().st_size, reverse=True)[:limit]
    return [
        {
            "path": path.relative_to(ROOT).as_posix(),
            "bytes": path.stat().st_size,
            "lines": len(_safe_text(path).splitlines()),
        }
        for path in files
    ]


def _successor_domain_imports() -> dict[str, list[str]]:
    apps = {
        "brand_experience": ROOT / "apps" / "brand_experience",
        "runtime_blueprints": ROOT / "apps" / "runtime_blueprints",
        "plans_entitlements": ROOT / "apps" / "plans_entitlements",
        "global_registries": ROOT / "apps" / "global_registries",
        "integrations_marketplace": ROOT / "apps" / "integrations_marketplace",
    }
    data: dict[str, list[str]] = {}
    for name, app_dir in apps.items():
        hits: list[str] = []
        for path in app_dir.rglob("*.py"):
            text = _safe_text(path)
            if "apps.siteconfig" in text:
                hits.append(path.relative_to(ROOT).as_posix())
        data[name] = hits
    return data


def _installed_app_count() -> int:
    settings_path = ROOT / "config" / "settings.py"
    text = _safe_text(settings_path)
    return len({match.group(1) for match in SETTINGS_APP_PATTERN.finditer(text)})


def _doc_drift() -> dict[str, object]:
    legacy_doc = ROOT / "docs" / "ALL_MODULES_COMPLETE_LIST.md"
    text = _safe_text(legacy_doc)
    doc_count = None
    match = re.search(r"\*\*Total Apps\*\*:\s*(\d+)\s+(?:Django Apps|Installed App Modules)", text)
    if match:
        doc_count = int(match.group(1))
    actual_count = _installed_app_count()
    return {
        "legacy_doc": legacy_doc.relative_to(ROOT).as_posix(),
        "documented_app_count": doc_count,
        "actual_installed_app_count": actual_count,
        "is_stale": doc_count != actual_count,
    }


def _public_endpoint_audits() -> dict[str, object]:
    csrf_path = ROOT / "scripts" / "allowlists" / "csrf_exempt_allowlist.json"
    allow_any_path = ROOT / "scripts" / "allowlists" / "allow_any_allowlist.json"
    csrf = json.loads(_safe_text(csrf_path)).get("files", {})
    allow_any = json.loads(_safe_text(allow_any_path)).get("files", {})
    return {
        "csrf_exempt": {
            "reviewed_files": len(csrf),
            "reviewed_endpoints": sum(int(entry.get("expected_count", 0)) for entry in csrf.values()),
            "owners": sorted({str(entry.get("owner", "")).strip() for entry in csrf.values() if str(entry.get("owner", "")).strip()}),
        },
        "allow_any": {
            "reviewed_files": len(allow_any),
            "reviewed_occurrences": sum(int(entry.get("expected_count", 0)) for entry in allow_any.values()),
            "owners": sorted({str(entry.get("owner", "")).strip() for entry in allow_any.values() if str(entry.get("owner", "")).strip()}),
        },
    }


def _to_markdown(inventory: dict[str, object]) -> str:
    metrics = inventory["baseline_counts"]
    doc_drift = inventory["doc_drift"]
    public_audits = inventory["public_endpoint_audits"]
    lines = [
        "# Platform Inventory",
        "",
        f"- Installed app modules: `{doc_drift['actual_installed_app_count']}`",
        f"- Python files: `{metrics['python_files']}`",
        f"- HTML templates: `{metrics['html_files']}`",
        f"- Markdown files: `{metrics['markdown_files']}`",
        f"- Migration files: `{metrics['migration_files']}`",
        f"- Management commands: `{metrics['management_commands']}`",
        f"- `SiteSettings` refs: `{metrics['site_settings']}`",
        f"- `get_solo()` refs: `{metrics['get_solo']}`",
        f"- `except Exception`: `{metrics['except_exception']}`",
        f"- `cursor.execute()`: `{metrics['cursor_execute']}`",
        f"- `csrf_exempt`: `{metrics['csrf_exempt']}`",
        f"- `AllowAny`: `{metrics['allow_any']}`",
        f"- `print()`: `{metrics['print_calls']}`",
        f"- `gilead` matches: `{metrics['gilead']}` across `{metrics['gilead_files']}` files",
        "",
        "## Public Endpoint Review",
        "",
        f"- Reviewed `csrf_exempt` files: `{public_audits['csrf_exempt']['reviewed_files']}`",
        f"- Reviewed `csrf_exempt` endpoints: `{public_audits['csrf_exempt']['reviewed_endpoints']}`",
        f"- Reviewed `AllowAny` files: `{public_audits['allow_any']['reviewed_files']}`",
        f"- Reviewed `AllowAny` occurrences: `{public_audits['allow_any']['reviewed_occurrences']}`",
        "",
        "## SiteSettings Ownership",
        "",
    ]
    owner_counts = Counter(item["owner"] for item in inventory["site_settings_fields"])
    for owner, count in sorted(owner_counts.items()):
        lines.append(f"- `{owner}`: `{count}` fields")
    lines.extend(
        [
            "",
            "## Successor Domain Imports Still Touching siteconfig",
            "",
        ]
    )
    for app_name, hits in inventory["successor_domain_imports"].items():
        lines.append(f"- `{app_name}`: `{len(hits)}` files")
    lines.extend(
        [
            "",
            "## Largest Python Files",
            "",
        ]
    )
    for entry in inventory["largest_python_files"]:
        lines.append(
            f"- `{entry['path']}`: `{entry['lines']}` lines / `{entry['bytes']}` bytes"
        )
    lines.extend(
        [
            "",
            "## Documentation Drift",
            "",
            f"- Legacy documented app count: `{doc_drift['documented_app_count']}`",
            f"- Actual installed app count: `{doc_drift['actual_installed_app_count']}`",
            f"- Drift detected: `{doc_drift['is_stale']}`",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def _build_inventory() -> dict[str, object]:
    return {
        "baseline_counts": _baseline_counts(),
        "public_endpoint_audits": _public_endpoint_audits(),
        "site_settings_fields": _site_settings_fields(),
        "largest_python_files": _largest_python_files(),
        "successor_domain_imports": _successor_domain_imports(),
        "doc_drift": _doc_drift(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate or verify the north-star platform inventory.")
    parser.add_argument("--write", action="store_true", help="Write inventory outputs to docs/generated.")
    parser.add_argument("--check", action="store_true", help="Fail if committed outputs do not match generated content.")
    args = parser.parse_args()

    inventory = _build_inventory()
    json_text = json.dumps(inventory, indent=2, sort_keys=True) + "\n"
    md_text = _to_markdown(inventory)

    if args.check:
        if not JSON_PATH.exists() or not MD_PATH.exists():
            print("platform inventory artifacts are missing; run with --write", file=sys.stderr)
            return 1
        if JSON_PATH.read_text(encoding="utf-8") != json_text or MD_PATH.read_text(encoding="utf-8") != md_text:
            print("platform inventory artifacts are stale; run scripts/generate_platform_inventory.py --write", file=sys.stderr)
            return 1
        print("generate_platform_inventory: committed inventory is up to date.")
        return 0

    if args.write:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        JSON_PATH.write_text(json_text, encoding="utf-8")
        MD_PATH.write_text(md_text, encoding="utf-8")
        print(f"generate_platform_inventory: wrote {JSON_PATH.relative_to(ROOT)} and {MD_PATH.relative_to(ROOT)}")
        return 0

    print(json_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
