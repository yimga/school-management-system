#!/usr/bin/env python3
"""
Verify TEST_MODULE_CANONICAL_MAP.md targets exist and SOT/log test references resolve.

Outputs docs/generated/test_module_contract.{json,md}. Exit 1 on unresolved modules.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP_PATH = ROOT / "docs" / "maintenance" / "TEST_MODULE_CANONICAL_MAP.md"
SOT_PATH = ROOT / "docs" / "RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md"
LOG_PATH = ROOT / "docs" / "RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md"
OUT_JSON = ROOT / "docs" / "generated" / "test_module_contract.json"
OUT_MD = ROOT / "docs" / "generated" / "test_module_contract.md"
EXTENSION_REGISTRY_PATH = ROOT / "apps" / "marketplace" / "extension_registry.py"
WEBHOOK_CATALOG_PATH = ROOT / "docs" / "developer" / "WEBHOOK_EVENT_CATALOG.md"

MODULE_RE = re.compile(
    r"\b(apps\.[a-zA-Z0-9_]+\.tests\.test_[a-zA-Z0-9_]+)\b"
)
ROW_RE = re.compile(
    r"^\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*$"
)


def _parse_map() -> list[tuple[str, str]]:
    if not MAP_PATH.is_file():
        return []
    rows: list[tuple[str, str]] = []
    for line in MAP_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
        m = ROW_RE.match(line.strip())
        if not m or m.group(1).strip().startswith("---") or m.group(1).strip() == "Prompt / legacy name":
            continue
        legacy = m.group(1).strip().strip("`")
        actual = m.group(2).strip().strip("`")
        if "actual module" in legacy.lower():
            continue
        rows.append((legacy, actual))
    return rows


def _resolve_module_path(mod: str) -> Path | None:
    """Return path to test module file if it exists."""
    p = ROOT / mod.replace(".", "/")
    if p.is_dir():
        p2 = p / "__init__.py"
        if p2.is_file():
            return p2
    p_py = Path(str(p) + ".py")
    if p_py.is_file():
        return p_py
    return None


def _module_resolves(mod: str, mapping: dict[str, str]) -> bool:
    if _resolve_module_path(mod) is not None:
        return True
    if mod in mapping and _resolve_module_path(mapping[mod]) is not None:
        return True
    return False


def _scan_unresolved(text: str, mapping: dict[str, str]) -> list[str]:
    bad: list[str] = []
    for m in MODULE_RE.finditer(text):
        mod = m.group(1)
        if _module_resolves(mod, mapping):
            continue
        bad.append(mod)
    return sorted(set(bad))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--strict-sot",
        action="store_true",
        help="Fail when SOT/log references a missing test module (default: map file only).",
    )
    args = ap.parse_args(argv)
    pairs = _parse_map()
    mapping = {a: b for a, b in pairs}
    missing_targets: list[str] = []
    for _legacy, actual in pairs:
        if _resolve_module_path(actual) is None:
            missing_targets.append(actual)

    sot = SOT_PATH.read_text(encoding="utf-8", errors="replace") if SOT_PATH.is_file() else ""
    log = LOG_PATH.read_text(encoding="utf-8", errors="replace") if LOG_PATH.is_file() else ""
    sot_scan = _scan_unresolved(sot + "\n" + log, mapping)
    unresolved = sot_scan if args.strict_sot else []
    extension_registry_present = EXTENSION_REGISTRY_PATH.is_file()
    webhook_catalog_present = WEBHOOK_CATALOG_PATH.is_file()

    ok = (
        not missing_targets
        and not unresolved
        and extension_registry_present
        and webhook_catalog_present
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ok": ok,
        "map_rows": len(pairs),
        "missing_map_targets": missing_targets,
        "unresolved_module_refs": unresolved,
        "sot_preflight_unresolved": sot_scan,
        "strict_sot": bool(args.strict_sot),
        "extension_registry_present": extension_registry_present,
        "webhook_catalog_present": webhook_catalog_present,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    OUT_MD.write_text(
        "\n".join(
            [
                "# Test module contract",
                "",
                f"**OK:** {ok}",
                "",
                f"**Missing map targets:** {missing_targets or '[]'}",
                f"**Unresolved:** {unresolved or '[]'}",
                f"**Extension registry present:** {extension_registry_present}",
                f"**Webhook catalog present:** {webhook_catalog_present}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print(f"verify_test_module_contract: {'OK' if ok else 'FAIL'} -> {OUT_JSON}")
    if not ok:
        if missing_targets:
            print(f"  missing files for mapped modules: {missing_targets}", file=sys.stderr)
        if unresolved:
            print(f"  unresolved refs: {unresolved}", file=sys.stderr)
        if not extension_registry_present:
            print(
                f"  missing extension registry: {EXTENSION_REGISTRY_PATH}",
                file=sys.stderr,
            )
        if not webhook_catalog_present:
            print(
                f"  missing webhook catalog: {WEBHOOK_CATALOG_PATH}",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
