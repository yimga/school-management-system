#!/usr/bin/env python3
"""Verify wizard step writers declare domain integration (stdlib-only).

Scans ``apps/setup_studio/wizards/*.json`` writer paths and checks resolver
function bodies for ``_try_domain_integration``, canonical service calls, or
explicit allow markers. Fails on cockpit-only writers for tenant-scoped wizards.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIZARD_DIR = ROOT / "apps" / "setup_studio" / "wizards"

_WRITER_RE = re.compile(
    r"^apps\.setup_studio\.(wizard_resolvers(?:_operator|_domain)?)::(?P<fn>write_[a-z0-9_]+)$"
)

_DOMAIN_MARKERS = (
    "_try_domain_integration",
    "schedule_dns_check",
    "bootstrap_migration_bundle",
    "link_guardian_to_student",
    "create_teacher_from_wizard",
    "create_student_from_wizard",
    "perform_password_rotation",
    "install_brand_assets",
    "compile_manifest",
    "set_runtime_default",
    "register_helpcenter_source",
    "register_upload",
    "compute_localized_price",
    "_write_to_site_settings",
    "wizard_complete_intent",
)

_ALLOW_COCKPIT_ONLY = frozenset(
    {
        # Operator scratch — no tenant yet
        "write_super_create_school_step",
        # Account-scoped MFA — secrets live in MFAEnrollment model
        "write_mfa_setup_step",
    }
)


def _load_function_sources() -> dict[str, tuple[str, str]]:
    modules = {
        "wizard_resolvers": ROOT / "apps/setup_studio/wizard_resolvers.py",
        "wizard_resolvers_operator": ROOT / "apps/setup_studio/wizard_resolvers_operator.py",
        "wizard_resolvers_domain": ROOT / "apps/setup_studio/wizard_resolvers_domain.py",
    }
    out: dict[str, tuple[str, str]] = {}
    for mod_name, path in modules.items():
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("write_"):
                segment = ast.get_source_segment(text, node) or ""
                out[node.name] = (mod_name, segment)
    return out


def _has_domain_hook(source: str) -> bool:
    return any(marker in source for marker in _DOMAIN_MARKERS)


def main() -> int:
    fn_sources = _load_function_sources()
    writers_seen: set[str] = set()
    failures: list[str] = []

    for path in sorted(WIZARD_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for step in data.get("steps") or []:
            writer = (step.get("persistence") or {}).get("writer") or ""
            m = _WRITER_RE.match(writer.strip())
            if not m:
                continue
            fn = m.group("fn")
            if fn in writers_seen:
                continue
            writers_seen.add(fn)
            if fn in _ALLOW_COCKPIT_ONLY:
                continue
            loc = fn_sources.get(fn)
            if loc is None:
                failures.append(f"missing writer function: {fn} ({path.name})")
                continue
            _mod, source = loc
            if not _has_domain_hook(source):
                failures.append(f"cockpit-only writer: {fn} ({_mod})")

    if failures:
        for item in failures:
            print(f"WIZARD_WRITER_COVERAGE_FAIL: {item}", file=sys.stderr)
        return 1
    print(f"WIZARD_WRITER_COVERAGE_PASS ({len(writers_seen)} writers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
