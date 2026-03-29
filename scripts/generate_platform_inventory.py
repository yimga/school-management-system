#!/usr/bin/env python3
"""
Generate the platform inventory required for the north-star hard-freeze phase.

Outputs:
- docs/generated/platform_inventory.json (+ `scoped_gravity_counts` for product-signal metrics)
- docs/generated/platform_inventory.md
- scripts/generated/scoped_gravity_trend.json (ring buffer of recent `scoped_gravity_counts`; under `scripts/` so keys matching **gilead** heuristics do not inflate `baseline_counts` scans of `docs/generated/*.json`)

Use `--write` to refresh committed artifacts and `--check` to fail CI when the
artifacts are stale, when **doc_drift.is_stale** is true, or when
**scoped_gravity_counts.print_calls_apps_py_excl_migrations_tests_management** ≠ 0 (P6).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / "docs" / "generated"
JSON_PATH = DOCS_DIR / "platform_inventory.json"
MD_PATH = DOCS_DIR / "platform_inventory.md"
TREND_PATH = ROOT / "scripts" / "generated" / "scoped_gravity_trend.json"

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
# Decorator-level CSRF exemptions (aligned with scripts/lint_csrf_exempt_usage.py).
CSRF_EXEMPT_DECORATOR_PATTERN = re.compile(
    r"^\s*@csrf_exempt\b|method_decorator\(\s*csrf_exempt\b"
)
SKIP_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "test-results",
    # IDE / agent artifacts under repo root can add/remove *.py and make --check flaky vs --write.
    ".cursor",
    ".idea",
    ".vscode",
}


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


def _management_commands_list() -> list[dict[str, str]]:
    """List all management commands (app, command name, relative path) for §10 inventory."""
    apps_dir = ROOT / "apps"
    if not apps_dir.is_dir():
        return []
    result: list[dict[str, str]] = []
    for path in sorted(apps_dir.rglob("management/commands/*.py")):
        if path.name == "__init__.py":
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        try:
            rel = path.relative_to(ROOT)
            # apps/<app>/management/commands/<name>.py
            parts = rel.parts
            if (
                len(parts) >= 4
                and parts[0] == "apps"
                and parts[2] == "management"
                and parts[3] == "commands"
            ):
                app_label = parts[1]
                command_name = path.stem
                result.append(
                    {
                        "app": app_label,
                        "command": command_name,
                        "path": rel.as_posix(),
                    }
                )
        except ValueError:
            continue
    return result


def _baseline_counts() -> dict[str, int]:
    counters = Counter()
    py_files = list(_iter_files(".py"))
    counters["python_files"] = len(py_files)
    counters["html_files"] = sum(1 for _ in _iter_files(".html"))
    counters["markdown_files"] = sum(1 for _ in _iter_files(".md"))
    counters["migration_files"] = sum(
        1 for path in py_files if "migrations" in path.parts
    )
    commands_list = _management_commands_list()
    counters["management_commands"] = len(commands_list)
    gilead_files = set()
    trend_rel = "scripts/generated/scoped_gravity_trend.json"
    file_pool = py_files + [
        p
        for p in _iter_files(".html", ".md", ".json", ".yaml", ".yml", ".sh", ".ps1")
        if p.relative_to(ROOT).as_posix() != trend_rel
    ]
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


def _path_has_excluded_part(path: Path, excluded: frozenset[str]) -> bool:
    return any(part in excluded for part in path.parts)


def _scoped_gravity_counts() -> dict[str, int]:
    """
    Product-facing counters (exclude migrations; some exclude tests/management).

    Gross `baseline_counts` mix migrations, tests, and docs-adjacent files—use these
    for SiteSettings / SQL / CSRF posture trends. The **gilead** line-hit tally matches
    ``lint_gilead_residue.py`` (skips ``apps/**/management/commands/``).
    """
    ss_pat = COUNT_PATTERNS["site_settings"]
    ce_pat = COUNT_PATTERNS["cursor_execute"]
    print_pat = COUNT_PATTERNS["print_calls"]
    gilead_pat = COUNT_PATTERNS["gilead"]

    def site_settings_apps_py(excluded: frozenset[str]) -> int:
        total = 0
        apps_dir = ROOT / "apps"
        if not apps_dir.is_dir():
            return 0
        for path in apps_dir.rglob("*.py"):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            if _path_has_excluded_part(path, excluded):
                continue
            total += len(ss_pat.findall(_safe_text(path)))
        return total

    def cursor_execute_apps_config_py(excluded: frozenset[str]) -> int:
        total = 0
        for root_name in ("apps", "config"):
            root = ROOT / root_name
            if not root.is_dir():
                continue
            for path in root.rglob("*.py"):
                if any(part in SKIP_PARTS for part in path.parts):
                    continue
                if _path_has_excluded_part(path, excluded):
                    continue
                total += len(ce_pat.findall(_safe_text(path)))
        return total

    def print_apps_py_product() -> int:
        """apps/**/*.py excluding migrations, tests, management (matches no-print gate spirit)."""
        total = 0
        apps_dir = ROOT / "apps"
        excluded = frozenset({"migrations", "tests", "management"})
        if not apps_dir.is_dir():
            return 0
        for path in apps_dir.rglob("*.py"):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            if _path_has_excluded_part(path, excluded):
                continue
            total += len(print_pat.findall(_safe_text(path)))
        return total

    def print_scripts_py() -> int:
        total = 0
        scripts_dir = ROOT / "scripts"
        if not scripts_dir.is_dir():
            return 0
        for path in scripts_dir.rglob("*.py"):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            total += len(print_pat.findall(_safe_text(path)))
        return total

    def csrf_exempt_decorator_lines_apps_config() -> int:
        total = 0
        for root_name in ("apps", "config"):
            root = ROOT / root_name
            if not root.is_dir():
                continue
            for path in root.rglob("*.py"):
                if any(part in SKIP_PARTS for part in path.parts):
                    continue
                if "migrations" in path.parts:
                    continue
                text = _safe_text(path)
                total += sum(
                    1
                    for line in text.splitlines()
                    if CSRF_EXEMPT_DECORATOR_PATTERN.search(line)
                )
        return total

    def gilead_line_hits_product_corpus() -> int:
        """Gilead string lines under apps, templates, config (no migrations/tests).

        Skips ``apps/**/management/commands/`` — same surface as ``lint_gilead_residue.py``
        (CLI-only; not HTTP/runtime-visible).
        """
        excluded = frozenset({"migrations", "tests"})
        roots = (ROOT / "apps", ROOT / "templates", ROOT / "config")
        total = 0
        for base in roots:
            if not base.exists():
                continue
            for path in base.rglob("*"):
                if not path.is_file():
                    continue
                if any(part in SKIP_PARTS for part in path.parts):
                    continue
                if _path_has_excluded_part(path, excluded):
                    continue
                rel = path.relative_to(ROOT).as_posix()
                if "management/commands/" in rel:
                    continue
                if path.suffix.lower() not in {".py", ".html"}:
                    continue
                text = _safe_text(path)
                total += sum(
                    1 for line in text.splitlines() if gilead_pat.search(line)
                )
        return total

    return {
        "site_settings_refs_apps_py_excl_migrations": site_settings_apps_py(
            frozenset({"migrations"})
        ),
        "site_settings_refs_apps_py_excl_migrations_tests": site_settings_apps_py(
            frozenset({"migrations", "tests"})
        ),
        "cursor_execute_apps_config_py_excl_migrations": cursor_execute_apps_config_py(
            frozenset({"migrations"})
        ),
        "print_calls_apps_py_excl_migrations_tests_management": print_apps_py_product(),
        "print_calls_scripts_py": print_scripts_py(),
        "csrf_exempt_decorator_lines_apps_config_excl_migrations": (
            csrf_exempt_decorator_lines_apps_config()
        ),
        "gilead_line_hits_apps_templates_config_excl_migrations_tests": (
            gilead_line_hits_product_corpus()
        ),
    }


def _largest_python_files(limit: int = 12) -> list[dict[str, int | str]]:
    files = sorted(
        _iter_files(".py"),
        key=lambda path: (-path.stat().st_size, path.relative_to(ROOT).as_posix()),
    )[:limit]
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
        data[name] = sorted(hits)
    return data


def _installed_app_count() -> int:
    settings_path = ROOT / "config" / "settings.py"
    text = _safe_text(settings_path)
    return len({match.group(1) for match in SETTINGS_APP_PATTERN.finditer(text)})


def _doc_drift() -> dict[str, object]:
    legacy_doc = ROOT / "docs" / "ALL_MODULES_COMPLETE_LIST.md"
    text = _safe_text(legacy_doc)
    doc_count = None
    match = re.search(
        r"\*\*Total Apps\*\*:\s*(\d+)\s+(?:Django Apps|Installed App Modules)", text
    )
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
            "reviewed_endpoints": sum(
                int(entry.get("expected_count", 0)) for entry in csrf.values()
            ),
            "owners": sorted(
                {
                    str(entry.get("owner", "")).strip()
                    for entry in csrf.values()
                    if str(entry.get("owner", "")).strip()
                }
            ),
        },
        "allow_any": {
            "reviewed_files": len(allow_any),
            "reviewed_occurrences": sum(
                int(entry.get("expected_count", 0)) for entry in allow_any.values()
            ),
            "owners": sorted(
                {
                    str(entry.get("owner", "")).strip()
                    for entry in allow_any.values()
                    if str(entry.get("owner", "")).strip()
                }
            ),
        },
    }


def _to_markdown(inventory: dict[str, object]) -> str:
    metrics = inventory["baseline_counts"]
    doc_drift = inventory["doc_drift"]
    public_audits = inventory["public_endpoint_audits"]
    scoped = inventory.get("scoped_gravity_counts") or {}
    lines = [
        "# Platform Inventory",
        "",
        f"- Installed app modules: `{doc_drift['actual_installed_app_count']}`",
        f"- Python files: `{metrics['python_files']}`",
        f"- HTML templates: `{metrics['html_files']}`",
        f"- Markdown files: `{metrics['markdown_files']}`",
        f"- Migration files: `{metrics['migration_files']}`",
        f"- Management commands: `{metrics['management_commands']}` (full list in JSON key `management_commands_list`)",
        f"- `SiteSettings` refs (gross scan): `{metrics['site_settings']}`",
        f"- `SiteSettings` refs (`apps/**/*.py`, excl. migrations): `{scoped.get('site_settings_refs_apps_py_excl_migrations', '—')}`",
        f"- `SiteSettings` refs (`apps/**/*.py`, excl. migrations+tests): `{scoped.get('site_settings_refs_apps_py_excl_migrations_tests', '—')}`",
        f"- `get_solo()` refs: `{metrics['get_solo']}`",
        f"- `except Exception`: `{metrics['except_exception']}`",
        f"- `cursor.execute()` (gross): `{metrics['cursor_execute']}`",
        f"- `cursor.execute()` (`apps`+`config` `.py`, excl. migrations): `{scoped.get('cursor_execute_apps_config_py_excl_migrations', '—')}`",
        f"- `csrf_exempt` (substring, gross): `{metrics['csrf_exempt']}`",
        f"- `csrf_exempt` decorator lines (`apps`+`config`, excl. migrations): `{scoped.get('csrf_exempt_decorator_lines_apps_config_excl_migrations', '—')}`",
        f"- `AllowAny`: `{metrics['allow_any']}`",
        f"- `print()` (gross all `.py`): `{metrics['print_calls']}`",
        f"- `print()` (`apps` product paths): `{scoped.get('print_calls_apps_py_excl_migrations_tests_management', '—')}`; `scripts/`: `{scoped.get('print_calls_scripts_py', '—')}`",
        f"- `gilead` matches (gross corpus): `{metrics['gilead']}` across `{metrics['gilead_files']}` files",
        f"- `gilead` line hits (`apps`+`templates`+`config`, excl. migrations+tests+`management/commands`): `{scoped.get('gilead_line_hits_apps_templates_config_excl_migrations_tests', '—')}`",
        "",
        "Gross totals include migrations and broad file pools; use **scoped** lines around SQL/SiteSettings/Tenant gravity for trend tracking (see SOT §0 *Structural remediation stack*).",
        f"- Scoped-gravity **history** (last writes): `scripts/generated/scoped_gravity_trend.json` (updated with `generate_platform_inventory.py --write`; excluded from gross `gilead` JSON scan).",
        "",
        "## Management Commands (full list)",
        "",
        f"Total: `{len(inventory['management_commands_list'])}` commands. First 25 by app/command:",
        "",
    ]
    for entry in inventory["management_commands_list"][:25]:
        lines.append(f"- `{entry['app']}` / `{entry['command']}` — `{entry['path']}`")
    rest = len(inventory["management_commands_list"]) - 25
    if rest > 0:
        lines.append(
            f"- … and {rest} more (see `platform_inventory.json` key `management_commands_list`)."
        )
    lines.extend(
        [
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
    )
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
        "scoped_gravity_counts": _scoped_gravity_counts(),
        "management_commands_list": _management_commands_list(),
        "public_endpoint_audits": _public_endpoint_audits(),
        "site_settings_fields": _site_settings_fields(),
        "largest_python_files": _largest_python_files(),
        "successor_domain_imports": _successor_domain_imports(),
        "doc_drift": _doc_drift(),
    }


def _normalized_scoped_counts(scoped: dict[str, object]) -> dict[str, int]:
    out: dict[str, int] = {}
    for k, v in sorted(scoped.items()):
        try:
            out[str(k)] = int(v)
        except (TypeError, ValueError):
            continue
    return out


def _update_scoped_gravity_trend(scoped: dict[str, int], *, max_points: int = 48) -> None:
    """Append or refresh a point in the ring buffer (dedupe identical consecutive counts)."""
    counts = _normalized_scoped_counts(scoped)
    point = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "counts": counts,
    }
    data: dict[str, object] = {"version": 1, "history": []}
    if TREND_PATH.is_file():
        try:
            raw = json.loads(TREND_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data = raw
        except (OSError, json.JSONDecodeError):
            pass
    hist = data.get("history")
    if not isinstance(hist, list):
        hist = []
    if (
        hist
        and isinstance(hist[-1], dict)
        and hist[-1].get("counts") == counts
    ):
        hist[-1] = point
    else:
        hist.append(point)
    data["history"] = hist[-max_points:]
    data["version"] = 1
    TREND_PATH.parent.mkdir(parents=True, exist_ok=True)
    TREND_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _verify_scoped_gravity_trend_matches(scoped: dict[str, int]) -> str | None:
    """Return error message if trend file exists but last point != current scoped counts."""
    if not TREND_PATH.is_file():
        return None
    try:
        raw = json.loads(TREND_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return f"scoped_gravity_trend.json invalid JSON: {e}"
    hist = raw.get("history")
    if not isinstance(hist, list) or not hist:
        return "scoped_gravity_trend.json has no history"
    last = hist[-1]
    if not isinstance(last, dict):
        return "scoped_gravity_trend.json last history entry is not an object"
    got = last.get("counts")
    if got != _normalized_scoped_counts(scoped):
        return (
            "scoped_gravity_trend.json last counts != current scoped_gravity_counts; "
            "run: python scripts/generate_platform_inventory.py --write"
        )
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate or verify the north-star platform inventory."
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write inventory outputs to docs/generated.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if committed outputs do not match generated content.",
    )
    args = parser.parse_args()

    inventory = _build_inventory()
    json_text = json.dumps(inventory, indent=2, sort_keys=True) + "\n"
    md_text = _to_markdown(inventory)

    if args.check:
        if not JSON_PATH.exists() or not MD_PATH.exists():
            print(
                "platform inventory artifacts are missing; run with --write",
                file=sys.stderr,
            )
            return 1
        doc_drift = inventory.get("doc_drift") or {}
        if doc_drift.get("is_stale"):
            print(
                "platform inventory: doc_drift.is_stale is true — align "
                f"`{doc_drift.get('legacy_doc', 'docs/ALL_MODULES_COMPLETE_LIST.md')}` "
                "app count with config/settings.py `apps.*` INSTALLED_APPS entries, "
                "then run: python scripts/generate_platform_inventory.py --write",
                file=sys.stderr,
            )
            return 1
        scoped = inventory.get("scoped_gravity_counts") or {}
        prints = scoped.get("print_calls_apps_py_excl_migrations_tests_management")
        if prints is None:
            print(
                "platform inventory: scoped_gravity_counts missing "
                "print_calls_apps_py_excl_migrations_tests_management; regenerate inventory",
                file=sys.stderr,
            )
            return 1
        if prints != 0:
            print(
                "platform inventory: scoped print_calls_apps_py_excl_migrations_tests_management "
                f"must be 0 for P6 merge bar (got {prints!r}); remove print() from apps product paths "
                "or run scripts/lint_no_print_in_apps.py",
                file=sys.stderr,
            )
            return 1
        if (
            JSON_PATH.read_text(encoding="utf-8") != json_text
            or MD_PATH.read_text(encoding="utf-8") != md_text
        ):
            print(
                "platform inventory artifacts are stale; run scripts/generate_platform_inventory.py --write",
                file=sys.stderr,
            )
            return 1
        trend_err = _verify_scoped_gravity_trend_matches(
            inventory.get("scoped_gravity_counts") or {}
        )
        if trend_err:
            print(f"platform inventory: {trend_err}", file=sys.stderr)
            return 1
        print("generate_platform_inventory: committed inventory is up to date.")
        return 0

    if args.write:
        DOCS_DIR.mkdir(parents=True, exist_ok=True)
        JSON_PATH.write_text(json_text, encoding="utf-8")
        MD_PATH.write_text(md_text, encoding="utf-8")
        _update_scoped_gravity_trend(inventory.get("scoped_gravity_counts") or {})
        print(
            f"generate_platform_inventory: wrote {JSON_PATH.relative_to(ROOT)}, "
            f"{MD_PATH.relative_to(ROOT)}, {TREND_PATH.relative_to(ROOT)}"
        )
        return 0

    print(json_text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
