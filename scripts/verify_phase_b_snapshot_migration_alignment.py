#!/usr/bin/env python3
"""
Phase B depth gate: ensure migration 0007 stays aligned with snapshot runtime module.

Run: ``raise SystemExit(main(None))`` (optional ``--base``; default is this repository root).
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Must stay aligned with PlatformPhaseBDomainSnapshot + migrations 0026–0027.
SNAPSHOT_MODEL_CLASS = "PlatformPhaseBDomainSnapshot"
ADDFIELD_MODEL_KW = "platformphasebdomainsnapshot"
EXPECTED_TYPED_METADATA_FIELDS: frozenset[str] = frozenset(
    {"payload_key_count", "payload_checksum", "payload_key_checksums"}
)

# Canonical Phase B snapshot domains (order-sensitive merge last wins — must match runtime tuple).
EXPECTED_PHASE_B_DOMAINS: tuple[str, ...] = (
    "design_studio",
    "documents",
    "global_registries",
    "marketplace_integrations",
    "metadata_governance",
    "plans_entitlements",
    "preview_platform",
    "reports",
    "runtime_blueprints",
    "policies_rules",
)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8", errors="replace"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Phase B snapshot migration alignment."
    )
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root (defaults to this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"--base directory not found: {raw_base}")
    return base


def _relative(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        base = _resolve_base(args.base)
    except ValueError as exc:
        return _fail([str(exc)])

    snapshot_module = (
        base / "apps" / "platform_runtime" / "phase_b_domain_snapshots.py"
    )
    migration_0007 = (
        base
        / "apps"
        / "platform_runtime"
        / "migrations"
        / "0007_platform_phase_b_domain_snapshots.py"
    )
    migration_0026 = (
        base
        / "apps"
        / "platform_runtime"
        / "migrations"
        / "0026_platformphasebdomainsnapshot_typed_metadata.py"
    )
    migration_0027 = (
        base
        / "apps"
        / "platform_runtime"
        / "migrations"
        / "0027_platformphasebdomainsnapshot_key_checksums.py"
    )
    models_py = base / "apps" / "platform_runtime" / "models.py"

    errors: list[str] = []

    if not snapshot_module.is_file():
        errors.append(f"Missing {_relative(snapshot_module, base)}")
    if not migration_0007.is_file():
        errors.append(f"Missing {_relative(migration_0007, base)}")
    if not migration_0026.is_file():
        errors.append(f"Missing {_relative(migration_0026, base)}")
    if not migration_0027.is_file():
        errors.append(f"Missing {_relative(migration_0027, base)}")
    if not models_py.is_file():
        errors.append(f"Missing {_relative(models_py, base)}")
    if errors:
        return _fail(errors)

    snap_tree = _parse(snapshot_module)
    mig_tree = _parse(migration_0007)
    mig_26_tree = _parse(migration_0026)
    mig_27_tree = _parse(migration_0027)
    models_tree = _parse(models_py)

    # Snapshot module must define PHASE_B_SNAPSHOT_DOMAINS tuple (v2: exact sequence match).
    domain_count = None
    domain_tuple: tuple[str, ...] | None = None
    for node in snap_tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "PHASE_B_SNAPSHOT_DOMAINS":
                    if isinstance(node.value, ast.Tuple):
                        domain_count = len(node.value.elts)
                        domain_tuple = _tuple_strings(node.value)
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "PHASE_B_SNAPSHOT_DOMAINS":
                if isinstance(node.value, ast.Tuple):
                    domain_count = len(node.value.elts)
                    domain_tuple = _tuple_strings(node.value)
    if domain_count is None:
        errors.append("phase_b_domain_snapshots.py missing tuple PHASE_B_SNAPSHOT_DOMAINS")
    elif domain_tuple is None:
        errors.append(
            "PHASE_B_SNAPSHOT_DOMAINS must be a tuple of string literals (update the verifier if format changed)"
        )
    elif domain_tuple != EXPECTED_PHASE_B_DOMAINS:
        errors.append(
            "PHASE_B_SNAPSHOT_DOMAINS drift vs verifier canonical tuple "
            f"(got {domain_tuple!r}, expected {EXPECTED_PHASE_B_DOMAINS!r})"
        )

    # v2: migration CreateModel must retain domain/payload/updated_at fields.
    if not _migration_create_model_fields_ok(mig_tree):
        errors.append(
            "migration 0007 CreateModel PlatformPhaseBDomainSnapshot missing expected fields "
            "(domain, payload, updated_at)"
        )

    # Migration 0007 seed must use historical model + slice helpers only: live
    # sync_phase_b_domain_snapshots_from_site writes payload_key_count / checksums
    # (0026–0027) and breaks migrate on a table that only has domain/payload/updated_at.
    imported_domains = False
    imported_snapshot_payload = False
    calls_live_sync = False
    uses_get_model_snapshot = False
    calls_update_or_create = False
    has_runpython = False
    depends_0162 = False

    for node in ast.walk(mig_tree):
        if isinstance(node, ast.ImportFrom) and node.module == "apps.platform_runtime.phase_b_domain_snapshots":
            names = {alias.name for alias in node.names}
            imported_domains |= "PHASE_B_SNAPSHOT_DOMAINS" in names
            imported_snapshot_payload |= "snapshot_payload_for_domain" in names
            if "sync_phase_b_domain_snapshots_from_site" in names:
                errors.append(
                    "migration 0007 must not import sync_phase_b_domain_snapshots_from_site "
                    "(uses ORM fields from later migrations); use PHASE_B_SNAPSHOT_DOMAINS + "
                    "snapshot_payload_for_domain + apps.get_model instead"
                )
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "sync_phase_b_domain_snapshots_from_site":
                calls_live_sync = True
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == "get_model":
                    if (
                        node.args
                        and isinstance(node.args[0], ast.Constant)
                        and node.args[0].value == "platform_runtime"
                        and len(node.args) > 1
                        and isinstance(node.args[1], ast.Constant)
                        and node.args[1].value == "PlatformPhaseBDomainSnapshot"
                    ):
                        uses_get_model_snapshot = True
                if node.func.attr == "update_or_create":
                    calls_update_or_create = True
                if node.func.attr == "RunPython":
                    has_runpython = True

    # dependency tuple contains ("siteconfig", "0162_phase_b_slim_sitesettings")
    for node in ast.walk(mig_tree):
        if isinstance(node, ast.Tuple) and len(node.elts) == 2:
            a, b = node.elts
            if isinstance(a, ast.Constant) and isinstance(b, ast.Constant):
                if a.value == "siteconfig" and b.value == "0162_phase_b_slim_sitesettings":
                    depends_0162 = True

    if not imported_domains:
        errors.append("migration 0007 missing import of PHASE_B_SNAPSHOT_DOMAINS")
    if not imported_snapshot_payload:
        errors.append("migration 0007 missing import of snapshot_payload_for_domain")
    if calls_live_sync:
        errors.append(
            "migration 0007 seed must not call sync_phase_b_domain_snapshots_from_site "
            "(breaks before 0026 columns exist)"
        )
    if not uses_get_model_snapshot:
        errors.append(
            "migration 0007 seed must use apps.get_model('platform_runtime', "
            "'PlatformPhaseBDomainSnapshot')"
        )
    if not calls_update_or_create:
        errors.append("migration 0007 seed must call update_or_create on the historical snapshot model")
    if not has_runpython:
        errors.append("migration 0007 missing migrations.RunPython(...) operation")
    if not depends_0162:
        errors.append("migration 0007 missing dependency on siteconfig.0162_phase_b_slim_sitesettings")
    if domain_count is not None and domain_count < len(EXPECTED_PHASE_B_DOMAINS):
        errors.append(
            f"PHASE_B_SNAPSHOT_DOMAINS unexpectedly small ({domain_count} "
            f"< {len(EXPECTED_PHASE_B_DOMAINS)})"
        )

    added_26 = _addfield_names_for_snapshot_model(mig_26_tree)
    added_27 = _addfield_names_for_snapshot_model(mig_27_tree)
    if not {"payload_key_count", "payload_checksum"} <= added_26:
        errors.append(
            "migration 0026 must AddField payload_key_count and payload_checksum "
            f"for {ADDFIELD_MODEL_KW} (got {sorted(added_26)!r})"
        )
    if "payload_key_checksums" not in added_27:
        errors.append(
            "migration 0027 must AddField payload_key_checksums "
            f"for {ADDFIELD_MODEL_KW} (got {sorted(added_27)!r})"
        )

    model_fields = _django_model_field_names(models_tree, SNAPSHOT_MODEL_CLASS)
    if model_fields is None:
        errors.append(
            f"{_relative(models_py, base)} missing class {SNAPSHOT_MODEL_CLASS}"
        )
    elif not EXPECTED_TYPED_METADATA_FIELDS <= model_fields:
        missing = sorted(EXPECTED_TYPED_METADATA_FIELDS - model_fields)
        errors.append(
            f"{SNAPSHOT_MODEL_CLASS} missing typed metadata fields {missing} "
            f"(have {sorted(model_fields)!r})"
        )

    if errors:
        return _fail(errors)

    print(
        "verify_phase_b_snapshot_migration_alignment: PASS "
        f"(snapshot_domains={domain_count}, migration_0007 historical seed wiring intact, "
        "0026-0027 + model typed metadata aligned)"
    )
    return 0


def _tuple_strings(tup: ast.Tuple) -> tuple[str, ...] | None:
    out: list[str] = []
    for elt in tup.elts:
        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
            out.append(elt.value)
        else:
            return None
    return tuple(out)


def _addfield_names_for_snapshot_model(mig_tree: ast.AST) -> set[str]:
    """Collect ``name=`` from ``migrations.AddField(model_name=platformphasebdomainsnapshot, ...)``."""
    out: set[str] = set()
    for node in ast.walk(mig_tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "AddField":
            continue
        model_name = _keyword_constant(node, "model_name")
        field_name = _keyword_constant(node, "name")
        if model_name == ADDFIELD_MODEL_KW and field_name:
            out.add(field_name)
    return out


def _keyword_constant(call: ast.Call, arg: str) -> str | None:
    for kw in call.keywords:
        if kw.arg != arg:
            continue
        if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def _django_model_field_names(tree: ast.AST, class_name: str) -> set[str] | None:
    """Best-effort: assignment targets in a Django ``models.Model`` subclass body."""
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


def _migration_create_model_fields_ok(mig_tree: ast.AST) -> bool:
    wanted = {"domain", "payload", "updated_at"}

    for node in ast.walk(mig_tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr != "CreateModel":
            continue
        name_kw = next((k for k in node.keywords if k.arg == "name"), None)
        if (
            not name_kw
            or not isinstance(name_kw.value, ast.Constant)
            or name_kw.value.value != "PlatformPhaseBDomainSnapshot"
        ):
            continue
        fields_kw = next((k for k in node.keywords if k.arg == "fields"), None)
        if not fields_kw or not isinstance(fields_kw.value, ast.List):
            return False
        found: set[str] = set()
        for elt in fields_kw.value.elts:
            if isinstance(elt, ast.Tuple) and elt.elts:
                key = elt.elts[0]
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    found.add(key.value)
        return wanted <= found
    return False


def _fail(errors: list[str]) -> int:
    print("verify_phase_b_snapshot_migration_alignment: FAIL", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(None))
