#!/usr/bin/env python3
"""
Static depth gate: siteconfig decomposition invariants (Phase B alignment).

No Django required. Ensures ``domain_ownership`` domains, Phase B snapshot domains,
and slim / RuntimeDefaults decomposition artifacts stay aligned (catch drift early).
Also requires ``docs/SITECONFIG_OWNERSHIP_MIGRATION.md`` to stay wired to this gate and to
the platform inventory **site_settings_refs** gravity metric + ``generate_platform_inventory.py``.
"""

from __future__ import annotations

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


def main() -> int:
    errors: list[str] = []

    plan_path = ROOT / "docs" / "SITECONFIG_OWNERSHIP_MIGRATION.md"
    if not plan_path.is_file():
        errors.append("Missing docs/SITECONFIG_OWNERSHIP_MIGRATION.md")
    else:
        plan_text = plan_path.read_text(encoding="utf-8", errors="replace")
        _plan_needles = (
            "verify_siteconfig_decomposition_depth.py",
            "site_settings_refs_apps_py_excl_migrations_tests",
            "generate_platform_inventory.py",
        )
        for needle in _plan_needles:
            if needle not in plan_text:
                errors.append(
                    "docs/SITECONFIG_OWNERSHIP_MIGRATION.md must reference "
                    f"{needle!r} (merge bar + scoped gravity / inventory train)"
                )

    dom_path = ROOT / "apps" / "siteconfig" / "domain_ownership.py"
    if not dom_path.is_file():
        errors.append(f"Missing {dom_path.relative_to(ROOT)}")
        return _fail(errors)

    snap_path = ROOT / "apps" / "platform_runtime" / "phase_b_domain_snapshots.py"
    if not snap_path.is_file():
        errors.append(f"Missing {snap_path.relative_to(ROOT)}")
        return _fail(errors)

    try:
        dom = _load_module("runmycampus_domain_ownership_static", dom_path)
        snap = _load_module("runmycampus_phase_b_snapshots_static", snap_path)
    except Exception as exc:  # pragma: no cover - defensive
        errors.append(f"Failed to import decomposition modules: {exc}")
        return _fail(errors)

    ownership_domains: tuple[str, ...] = getattr(dom, "OWNERSHIP_DOMAINS", ())
    exact: dict[str, str] = getattr(dom, "EXACT_FIELD_OWNERS", {})
    prefixes: tuple[tuple[str, str], ...] = getattr(dom, "PREFIX_FIELD_OWNERS", ())
    phase_b_domains: tuple[str, ...] = getattr(snap, "PHASE_B_SNAPSHOT_DOMAINS", ())

    ownership_set = set(ownership_domains)
    if len(ownership_domains) != len(ownership_set):
        errors.append("OWNERSHIP_DOMAINS contains duplicates")

    if not phase_b_domains:
        errors.append("PHASE_B_SNAPSHOT_DOMAINS is empty")

    # Merge contract: policies_rules last (portal/feature flags win on overlaps).
    if phase_b_domains and phase_b_domains[-1] != "policies_rules":
        errors.append(
            "PHASE_B_SNAPSHOT_DOMAINS must end with 'policies_rules' (stable merge order)"
        )

    if "brand_experience" in phase_b_domains:
        errors.append(
            "brand_experience must not appear in PHASE_B_SNAPSHOT_DOMAINS "
            "(authority: PlatformGlobalBranding / Batch 1)"
        )

    for d in phase_b_domains:
        if d not in ownership_set:
            errors.append(
                f"PHASE_B_SNAPSHOT_DOMAINS domain {d!r} is missing from OWNERSHIP_DOMAINS"
            )

    for field, owner in exact.items():
        if owner not in ownership_set:
            errors.append(
                f"EXACT_FIELD_OWNERS[{field!r}] owner {owner!r} not in OWNERSHIP_DOMAINS"
            )

    for prefix, owner in prefixes:
        if owner not in ownership_set:
            errors.append(
                f"PREFIX_FIELD_OWNERS prefix {prefix!r} owner {owner!r} not in OWNERSHIP_DOMAINS"
            )

    slim = ROOT / "apps" / "siteconfig" / "sitesettings_slim_contract.py"
    if not slim.is_file():
        errors.append("Missing apps/siteconfig/sitesettings_slim_contract.py")
    else:
        slim_text = slim.read_text(encoding="utf-8", errors="replace")
        if "SITESETTINGS_SLIM_LOCAL_CONCRETE_FIELD_NAMES" not in slim_text:
            errors.append(
                "sitesettings_slim_contract.py missing SITESETTINGS_SLIM_LOCAL_CONCRETE_FIELD_NAMES"
            )
        # Keep the slim row contract explicit (Phase B Batch 0).
        for col in ("id", "maintenance_mode", "updated_at"):
            needle = f'"{col}"'
            if needle not in slim_text:
                errors.append(
                    f"sitesettings_slim_contract.py must document/include slim column {col!r}"
                )

    rdfc = ROOT / "apps" / "platform_runtime" / "runtime_defaults_first_class.py"
    if not rdfc.is_file():
        errors.append("Missing apps/platform_runtime/runtime_defaults_first_class.py")
    else:
        rdfc_text = rdfc.read_text(encoding="utf-8", errors="replace")
        if "RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES" not in rdfc_text:
            errors.append(
                "runtime_defaults_first_class.py missing RUNTIME_DEFAULTS_FIRST_CLASS_FIELD_NAMES"
            )

    if errors:
        return _fail(errors)

    print(
        "verify_siteconfig_decomposition_depth: PASS "
        f"(domains={len(ownership_domains)}, phase_b_snapshot_domains={len(phase_b_domains)}, "
        f"exact_fields={len(exact)})"
    )
    return 0


def _fail(errors: list[str]) -> int:
    print("verify_siteconfig_decomposition_depth: FAIL", file=sys.stderr)
    for err in errors:
        print(f"  - {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
