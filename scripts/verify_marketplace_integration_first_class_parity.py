#!/usr/bin/env python3
"""
Marketplace integration secrets stay first-class on RuntimeDefaults (credential migrations **0029**–**0034**).

``0035`` is the **PlatformIntegrationWebhookEvent** audit table, not a new marketplace secret column.
When product adds another credential-like key to ``get_marketplace_integration_settings``, this script fails until:

1. ``RuntimeDefaults`` gains a typed column + migration (**0037+** — **0036** is ``PlatformReportPlatformSkuDefault``, not a marketplace dict key),
2. ``RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES`` / string blanking set include the key,
3. ``_MARKETPLACE_SECRET_KEYS`` includes it (Phase B snapshots must strip it).

No Django setup required (AST + importlib only).

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify marketplace integration first-class parity."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root to inspect (default: this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"Base path is not a directory: {base}")
    return base


def _relative(path: Path, base: Path) -> Path | str:
    try:
        return path.relative_to(base)
    except ValueError:
        return path


def _credential_like_key(name: str) -> bool:
    """Heuristic: keys that must not ship only in JSON / Phase B marketplace snapshots."""
    n = name.lower()
    return any(
        s in n
        for s in (
            "api_key",
            "_token",
            "token",
            "_secret",
            "secret",
            "password",
        )
    )


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8", errors="replace"))


def _marketplace_integration_literal_keys(tree: ast.AST) -> list[str] | None:
    """String keys from ``return { ... }`` in ``SiteSettings.get_marketplace_integration_settings``."""
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "SiteSettings":
            continue
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            if item.name != "get_marketplace_integration_settings":
                continue
            for stmt in item.body:
                if not isinstance(stmt, ast.Return) or stmt.value is None:
                    continue
                val = stmt.value
                if not isinstance(val, ast.Dict):
                    return None
                keys: list[str] = []
                for k in val.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        keys.append(k.value)
                    else:
                        return None
                return keys
    return None


def _django_model_assign_field_names(tree: ast.AST, class_name: str) -> set[str] | None:
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        names: set[str] = set()
        for stmt in node.body:
            if isinstance(stmt, ast.Assign):
                for t in stmt.targets:
                    if isinstance(t, ast.Name) and t.id != "Meta":
                        names.add(t.id)
        return names
    return None


def main(argv: list[str] | None = None) -> int:
    errors: list[str] = []
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        return _fail([str(exc)])

    siteconfig_models = root / "apps" / "siteconfig" / "models.py"
    platform_models = root / "apps" / "platform_runtime" / "models.py"
    snapshot_module = root / "apps" / "platform_runtime" / "phase_b_domain_snapshots.py"
    first_class_module = (
        root / "apps" / "platform_runtime" / "runtime_defaults_first_class.py"
    )

    for p in (
        siteconfig_models,
        platform_models,
        snapshot_module,
        first_class_module,
    ):
        if not p.is_file():
            errors.append(f"Missing {_relative(p, root)}")

    if errors:
        return _fail(errors)

    snap_mod = _load_module("phase_b_snapshots_gate", snapshot_module)
    fc_mod = _load_module("runtime_defaults_fc_gate", first_class_module)
    strip_keys: frozenset[str] = snap_mod._MARKETPLACE_SECRET_KEYS
    first_class: tuple[str, ...] = fc_mod.RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES
    first_class_set = set(first_class)

    site_tree = _parse(siteconfig_models)
    plat_tree = _parse(platform_models)

    mk_keys = _marketplace_integration_literal_keys(site_tree)
    if mk_keys is None:
        errors.append(
            "Could not parse SiteSettings.get_marketplace_integration_settings "
            "return dict (keep a literal dict with string literal keys for this gate)"
        )
    else:
        mk_set = set(mk_keys)
        cred_in_dict = {k for k in mk_set if _credential_like_key(k)}
        if cred_in_dict != set(strip_keys):
            errors.append(
                "Credential-like keys in get_marketplace_integration_settings must match "
                f"_MARKETPLACE_SECRET_KEYS exactly.\n"
                f"  dict (credential-like): {sorted(cred_in_dict)!r}\n"
                f"  _MARKETPLACE_SECRET_KEYS: {sorted(strip_keys)!r}\n"
                "  When adding a new secret: add typed RuntimeDefaults column + migration 0039+, "
                "extend RUNTIME_DEFAULTS_FIRST_CLASS_*, then add the key to _MARKETPLACE_SECRET_KEYS."
            )
        for k in strip_keys:
            if k not in mk_set:
                errors.append(
                    f"_MARKETPLACE_SECRET_KEYS contains {k!r} missing from "
                    "get_marketplace_integration_settings return dict"
                )
            if k not in first_class_set:
                errors.append(
                    f"Marketplace secret {k!r} must appear in "
                    "RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES (first-class marketplace secret pattern)"
                )

    rd_names = _django_model_assign_field_names(plat_tree, "RuntimeDefaults")
    if rd_names is None:
        errors.append(
            f"{_relative(platform_models, root)} missing class RuntimeDefaults"
        )
    else:
        for k in strip_keys:
            if k not in rd_names:
                errors.append(
                    f"RuntimeDefaults model missing field {k!r} "
                    "(typed column required for marketplace secret)"
                )

    if errors:
        return _fail(errors)

    print(
        "verify_marketplace_integration_first_class_parity: PASS "
        f"(secrets={sorted(strip_keys)!r} aligned with dict, first-class tuple, RuntimeDefaults)"
    )
    return 0


def _fail(errors: list[str]) -> int:
    print("verify_marketplace_integration_first_class_parity: FAIL", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(None))
