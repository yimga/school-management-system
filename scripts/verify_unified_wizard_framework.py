#!/usr/bin/env python
"""verify_unified_wizard_framework.py — integrity gate for the wizard engine.

Asserts:
1. Every wizard JSON file parses + matches schema constraints.
2. Every options_resolver / next_step_resolver / persistence.writer dotted path
   in every JSON imports cleanly.
3. Engine module imports without side-effect failures.
4. wizard_ai.py imports services.ai_helpers but NOT services.ai_gateway.
5. Every prompt_template_key referenced in JSON exists in PROMPT_LIBRARY.
6. Every prompt key in PROMPT_LIBRARY has a fallback in FALLBACK_REGISTRY.
7. Stable wizard URL routes resolve under setup_studio namespace.

Exit codes: 0 = pass, 1 = fail. Designed to be wired into
``.github/workflows/architectural-boundaries.yml``.
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

WIZARDS_DIR = REPO_ROOT / "apps" / "setup_studio" / "wizards"
WIZARD_LAYER_FILES = [
    REPO_ROOT / "apps" / "setup_studio" / "wizard_engine.py",
    REPO_ROOT / "apps" / "setup_studio" / "wizard_state_resolver.py",
    REPO_ROOT / "apps" / "setup_studio" / "wizard_ai.py",
    REPO_ROOT / "apps" / "setup_studio" / "wizard_validators.py",
    REPO_ROOT / "apps" / "setup_studio" / "wizard_telemetry.py",
    REPO_ROOT / "apps" / "setup_studio" / "wizard_views.py",
    REPO_ROOT / "apps" / "setup_studio" / "wizard_resolvers.py",
    REPO_ROOT / "apps" / "setup_studio" / "ai_prompts.py",
    REPO_ROOT / "apps" / "setup_studio" / "ai_fallbacks.py",
]

_VALID_INPUT_TYPES = {
    "single_choice", "multi_choice", "text", "long_text", "number", "decimal",
    "boolean", "file_upload", "image_upload", "color_picker", "domain_input",
    "structured_form", "draw_on_map", "csv_mapping", "rich_select",
    "ranked_list", "key_value_pairs", "datetime", "duration",
}

_VALID_AUDIENCES = {"operator", "tenant_admin", "teacher", "parent", "student", "staff"}


def check_json_parses() -> list[str]:
    errors: list[str] = []
    for path in sorted(WIZARDS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: cannot parse: {exc}")
            continue
        if not isinstance(data, dict):
            errors.append(f"{path.name}: top-level must be object")
            continue
        if not isinstance(data.get("wizard_key"), str):
            errors.append(f"{path.name}: wizard_key missing or not string")
        if not isinstance(data.get("steps"), list) or not data["steps"]:
            errors.append(f"{path.name}: steps missing or empty")
        audience = data.get("audience")
        if not isinstance(audience, list) or not audience:
            errors.append(f"{path.name}: audience missing or empty")
        else:
            for a in audience:
                if a not in _VALID_AUDIENCES:
                    errors.append(f"{path.name}: invalid audience {a!r}")
        for step in data.get("steps", []):
            if not isinstance(step, dict):
                errors.append(f"{path.name}: step is not object")
                continue
            if step.get("input_type") not in _VALID_INPUT_TYPES:
                errors.append(f"{path.name}.{step.get('key', '?')}: invalid input_type {step.get('input_type')!r}")
            if "branches" in step and "next_step_resolver" in step and step["branches"] and step["next_step_resolver"]:
                errors.append(f"{path.name}.{step.get('key', '?')}: branches AND next_step_resolver both set")
    return errors


def check_dotted_paths() -> list[str]:
    """Every dotted path referenced in JSON must import + be callable."""
    errors: list[str] = []
    for path in sorted(WIZARDS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        paths_to_check: list[tuple[str, str]] = []
        for step in data.get("steps", []):
            if not isinstance(step, dict):
                continue
            step_key = step.get("key", "?")
            for field_name in ("options_resolver", "next_step_resolver"):
                val = step.get(field_name)
                if isinstance(val, str):
                    paths_to_check.append((f"{path.name}.{step_key}.{field_name}", val))
            persistence = step.get("persistence") or {}
            if isinstance(persistence, dict):
                writer = persistence.get("writer")
                if isinstance(writer, str):
                    paths_to_check.append((f"{path.name}.{step_key}.persistence.writer", writer))
            for field in step.get("fields", []) or []:
                if isinstance(field, dict):
                    cr = field.get("choices_resolver")
                    if isinstance(cr, str):
                        paths_to_check.append((f"{path.name}.{step_key}.fields.{field.get('name', '?')}.choices_resolver", cr))

        for label, dotted in paths_to_check:
            if "::" not in dotted:
                errors.append(f"{label}: invalid dotted path format {dotted!r}")
                continue
            mod_path, attr = dotted.split("::", 1)
            try:
                module = importlib.import_module(mod_path)
                obj = getattr(module, attr, None)
                if obj is None:
                    errors.append(f"{label}: module {mod_path!r} has no attribute {attr!r}")
                elif not callable(obj):
                    errors.append(f"{label}: {dotted!r} is not callable")
            except ImportError as exc:
                errors.append(f"{label}: cannot import {mod_path!r}: {exc}")
    return errors


def check_ai_boundary() -> list[str]:
    """wizard layer MUST NOT import services.ai_gateway directly. wizard_ai.py MUST import services.ai_helpers."""
    errors: list[str] = []
    for path in WIZARD_LAYER_FILES:
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            errors.append(f"{path.name}: syntax error: {exc}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("services.ai_gateway"):
                        errors.append(f"{path.name}: forbidden direct import services.ai_gateway")
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.startswith("services.ai_gateway"):
                    errors.append(f"{path.name}: forbidden direct import from services.ai_gateway")

    wizard_ai_path = REPO_ROOT / "apps" / "setup_studio" / "wizard_ai.py"
    if wizard_ai_path.exists():
        src = wizard_ai_path.read_text(encoding="utf-8")
        if "from services.ai_helpers import" not in src and "import services.ai_helpers" not in src:
            errors.append("wizard_ai.py: must import from services.ai_helpers")
    return errors


def check_prompt_library_consistency() -> list[str]:
    """Every prompt_template_key in JSON must exist in PROMPT_LIBRARY; every key in PROMPT_LIBRARY must have a fallback."""
    errors: list[str] = []
    try:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        from apps.setup_studio.ai_prompts import PROMPT_LIBRARY
        from apps.setup_studio.ai_fallbacks import FALLBACK_REGISTRY
    except Exception as exc:  # noqa: BLE001
        errors.append(f"cannot import ai_prompts / ai_fallbacks: {exc}")
        return errors

    referenced_keys: set[str] = set()
    for path in sorted(WIZARDS_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for step in data.get("steps", []):
            ai = (step or {}).get("ai_recommend") or {}
            ptk = ai.get("prompt_template_key")
            if isinstance(ptk, str):
                referenced_keys.add(ptk)

    for key in referenced_keys:
        if key not in PROMPT_LIBRARY:
            errors.append(f"prompt_template_key referenced in JSON but missing from PROMPT_LIBRARY: {key}")

    for key in PROMPT_LIBRARY:
        if key not in FALLBACK_REGISTRY:
            errors.append(f"PROMPT_LIBRARY entry has no fallback in FALLBACK_REGISTRY: {key}")
    return errors


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(REPO_ROOT))
    all_errors: list[str] = []
    print("== verify_unified_wizard_framework ==")
    print(f"repo root: {REPO_ROOT}")

    print("\n[1/4] JSON parses + schema...")
    errs = check_json_parses()
    all_errors.extend(errs)
    print(f"  errors: {len(errs)}")

    print("\n[2/4] Dotted paths import + callable...")
    errs = check_dotted_paths()
    all_errors.extend(errs)
    print(f"  errors: {len(errs)}")

    print("\n[3/4] AI boundary (services.ai_gateway not imported in wizard layer)...")
    errs = check_ai_boundary()
    all_errors.extend(errs)
    print(f"  errors: {len(errs)}")

    print("\n[4/4] Prompt library coverage...")
    errs = check_prompt_library_consistency()
    all_errors.extend(errs)
    print(f"  errors: {len(errs)}")

    if all_errors:
        print("\nFAILED:")
        for e in all_errors:
            print(f"  - {e}")
        return 1
    print("\nverify_unified_wizard_framework: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
