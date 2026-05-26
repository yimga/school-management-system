#!/usr/bin/env python
"""scan_wizard_json_schema_drift.py — zero-tolerance gate (baseline 0).

Validates every wizard JSON file against the documented schema invariants.
Mirrors the architectural-boundaries.yml pattern: exits 1 on any drift.

Invariants enforced (per docs/plans/UNIFIED_WIZARD_FRAMEWORK_IMPLEMENTATION_DETAIL.md §2):
* wizard_key matches ``^[a-z][a-z0-9_]*$``
* version >= 1
* audience non-empty list, values in known set
* steps non-empty list, max 8 steps
* each step has key + input_type
* input_type in known set
* branches and next_step_resolver mutually exclusive
* options_resolver / next_step_resolver / persistence.writer use ``module::callable`` format
* label_token matches ``^wizards\\.<wizard_key>\\.(label|description|step\\.<step_key>\\.(label|description)|.*)$``
  (i.e. namespaced under wizards.)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WIZARDS_DIR = REPO_ROOT / "apps" / "setup_studio" / "wizards"

_VALID_INPUT_TYPES = {
    "single_choice", "multi_choice", "text", "long_text", "number", "decimal",
    "boolean", "file_upload", "image_upload", "color_picker", "domain_input",
    "structured_form", "draw_on_map", "csv_mapping", "rich_select",
    "ranked_list", "key_value_pairs", "datetime", "duration",
}
_VALID_AUDIENCES = {"operator", "tenant_admin", "teacher", "parent", "student", "staff"}

_WIZARD_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_STEP_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_TOKEN_PREFIX_RE = re.compile(r"^wizards\.")
_DOTTED_PATH_RE = re.compile(r"^apps\.[a-z_.]+::[a-z_]+$")
_ICON_RE = re.compile(r"^rmc-icon-[a-z-]+$")


def scan_file(path: Path) -> list[str]:
    errors: list[str] = []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path.name}: cannot parse: {exc}"]

    if not isinstance(data, dict):
        return [f"{path.name}: top-level must be object"]

    wizard_key = data.get("wizard_key")
    if not isinstance(wizard_key, str) or not _WIZARD_KEY_RE.match(wizard_key):
        errors.append(f"{path.name}: wizard_key {wizard_key!r} does not match pattern")
        return errors

    if path.stem != wizard_key:
        errors.append(f"{path.name}: filename does not match wizard_key {wizard_key!r}")

    version = data.get("version")
    if not isinstance(version, int) or version < 1:
        errors.append(f"{wizard_key}: version must be integer >= 1")

    audience = data.get("audience")
    if not isinstance(audience, list) or not audience:
        errors.append(f"{wizard_key}: audience must be non-empty list")
    else:
        for a in audience:
            if a not in _VALID_AUDIENCES:
                errors.append(f"{wizard_key}: invalid audience {a!r}")

    label_token = data.get("label_token")
    if not isinstance(label_token, str) or not _TOKEN_PREFIX_RE.match(label_token):
        errors.append(f"{wizard_key}: label_token must start with 'wizards.'")

    icon = data.get("icon_class")
    if isinstance(icon, str) and not _ICON_RE.match(icon):
        errors.append(f"{wizard_key}: icon_class {icon!r} should match ^rmc-icon-[a-z-]+$")

    em = data.get("estimated_minutes")
    if not isinstance(em, int) or em < 1 or em > 60:
        errors.append(f"{wizard_key}: estimated_minutes must be integer in 1..60")

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        errors.append(f"{wizard_key}: steps must be non-empty list")
        return errors
    if len(steps) > 8:
        errors.append(f"{wizard_key}: max 8 steps per wizard ({len(steps)} found)")

    step_keys_seen: set[str] = set()
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            errors.append(f"{wizard_key}.[step #{i}]: not an object")
            continue
        sk = step.get("key")
        if not isinstance(sk, str) or not _STEP_KEY_RE.match(sk):
            errors.append(f"{wizard_key}.[step #{i}]: invalid step key {sk!r}")
            continue
        if sk in step_keys_seen:
            errors.append(f"{wizard_key}.{sk}: duplicate step key")
        step_keys_seen.add(sk)

        it = step.get("input_type")
        if it not in _VALID_INPUT_TYPES:
            errors.append(f"{wizard_key}.{sk}: invalid input_type {it!r}")

        has_branches = bool(step.get("branches"))
        has_resolver = bool(step.get("next_step_resolver"))
        if has_branches and has_resolver:
            errors.append(f"{wizard_key}.{sk}: branches AND next_step_resolver both set")

        for fname in ("options_resolver", "next_step_resolver"):
            val = step.get(fname)
            if val is not None and not _DOTTED_PATH_RE.match(str(val)):
                errors.append(f"{wizard_key}.{sk}.{fname}: invalid dotted path {val!r}")

        persistence = step.get("persistence") or {}
        if isinstance(persistence, dict):
            writer = persistence.get("writer")
            if writer is not None and not _DOTTED_PATH_RE.match(str(writer)):
                errors.append(f"{wizard_key}.{sk}.persistence.writer: invalid dotted path {writer!r}")

        fields = step.get("fields") or []
        for fld in fields:
            if not isinstance(fld, dict):
                errors.append(f"{wizard_key}.{sk}.fields: entry is not object")
                continue
            fn = fld.get("name")
            if not isinstance(fn, str) or not _STEP_KEY_RE.match(fn):
                errors.append(f"{wizard_key}.{sk}.fields: invalid field name {fn!r}")

    return errors


def main(argv: list[str]) -> int:
    print("== scan_wizard_json_schema_drift (baseline 0) ==")
    all_errors: list[str] = []
    for path in sorted(WIZARDS_DIR.glob("*.json")):
        if path.name.startswith("_"):
            continue
        all_errors.extend(scan_file(path))

    if all_errors:
        print(f"\nFAILED — {len(all_errors)} schema drift finding(s):")
        for e in all_errors:
            print(f"  - {e}")
        return 1
    print(f"\nscan_wizard_json_schema_drift: PASS (0 findings)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
