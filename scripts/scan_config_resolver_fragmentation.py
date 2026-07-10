#!/usr/bin/env python3
"""Config-resolver adoption ratchet (9.8-regime config-SOT wave, 2026-07-05).

The platform has ONE merged config resolver
(``apps/platform_runtime/helpers.py::get_effective_site_settings`` — precedence
RuntimeDefaults -> School.settings -> wizard overlay, request/TTL cached) and
TWO canonical read facades over it:

* ``apps.platform_runtime.config_resolver.get_effective_config(school, key)``
  — the single-KEY read (Wave A, `aa43a98d6`);
* ``apps.siteconfig.config_service`` — typed per-DOMAIN config objects.

The read-side fragmentation is the long tail of consumer sites that grab the
raw effective namespace (``get_effective_site_settings(...)``, the
``get_legacy_site_settings_compat`` bridge, or — worst — the raw singleton
handle ``get_platform_site_settings_record``) and attribute-fan-out from it.
Those sites bypass every future choke point (draft/preview/publish, per-key
ownership routing, decision logging) that the keyed facade exists to host.

This gate does NOT consolidate anything — it counts the fragmented call-sites
into a baseline that can only go DOWN, so the tail stops growing while the
adoption waves migrate it. New code reads ONE key via ``get_effective_config``
or a DOMAIN object via ``config_service`` — never one more raw-namespace grab.

Facade harmony note (contradiction closed 2026-07-05): ``config_service`` and
``get_effective_config`` are complementary layers over the same resolver, not
rivals — key-shaped reads use the keyed accessor, domain-shaped reads use the
domain facade. Both inherit precedence + caching from the merged resolver.

Usage:
  python scripts/scan_config_resolver_fragmentation.py            # report
  python scripts/scan_config_resolver_fragmentation.py --compare  # CI gate
  python scripts/scan_config_resolver_fragmentation.py --update-baseline

Mark deliberate sites with ``# config-resolver-allow: <reason>`` on the call
line or the line above. ``--compare`` is line-insensitive (keyed on the
``(path, name)`` multiset) so cosmetic drift never trips it; one MORE raw
read in a file does.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "var" / "security-audit-baseline-config-resolver-fragmentation.json"

FRAGMENTED_READERS = {
    # Raw effective-namespace grab + attribute fan-out (the ~200-site tail).
    "get_effective_site_settings",
    # Explicit compat bridge — existing callers frozen, new callers forbidden.
    "get_legacy_site_settings_compat",
    # Raw ORM singleton handle — never a read path for product code.
    "get_platform_site_settings_record",
}

# Canonical/definition modules are exempt: the resolver family may LIVE there
# and delegate to itself; the ratchet targets consumer sprawl, not the SOT.
EXEMPT_PARTS = {"tests", "migrations"}
EXEMPT_FILES = {
    Path("apps/platform_runtime/helpers.py"),
    Path("apps/platform_runtime/config_resolver.py"),
    Path("apps/platform_runtime/site_settings_read_access.py"),
    Path("apps/platform_runtime/runtime_resolver.py"),
    Path("apps/platform_runtime/runtime_defaults_first_class.py"),
    Path("apps/siteconfig/config_service.py"),
}

SCAN_ROOTS = ("apps", "services")


def _allowed(lines: list[str], lineno: int) -> bool:
    for idx in (lineno - 1, lineno - 2):
        if 0 <= idx < len(lines) and "config-resolver-allow:" in lines[idx]:
            return True
    return False


def scan() -> list[dict]:
    findings: list[dict] = []
    for root in SCAN_ROOTS:
        base = ROOT / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            rel = path.relative_to(ROOT)
            if EXEMPT_PARTS.intersection(rel.parts) or rel in EXEMPT_FILES:
                continue
            if rel.name.startswith("test_"):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
                tree = ast.parse(text)
            except SyntaxError:
                continue
            lines = text.splitlines()
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name in FRAGMENTED_READERS and not _allowed(lines, node.lineno):
                    findings.append(
                        {"path": rel.as_posix(), "name": name, "line": node.lineno}
                    )
    return findings


def _multiset(findings: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        key = f"{f['path']}::{f['name']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()

    findings = scan()
    if args.update_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps(
                {"finding_count": len(findings), "findings": findings}, indent=2
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"baseline written: {len(findings)} finding(s)")
        return 0

    if args.compare:
        if not BASELINE.is_file():
            print("no baseline; run --update-baseline first", file=sys.stderr)
            return 1
        base = json.loads(BASELINE.read_text(encoding="utf-8"))
        base_counts = _multiset(base.get("findings", []))
        cur_counts = _multiset(findings)
        new = {
            k: (v, base_counts.get(k, 0))
            for k, v in cur_counts.items()
            if v > base_counts.get(k, 0)
        }
        if new:
            print("config-resolver fragmentation GREW (ratchet is one-way):", file=sys.stderr)
            for key, (cur, prev) in sorted(new.items()):
                print(f"  {key}: {prev} -> {cur}", file=sys.stderr)
            print(
                "Read ONE key via apps.platform_runtime.config_resolver."
                "get_effective_config, or a DOMAIN object via"
                " apps.siteconfig.config_service, or add"
                " '# config-resolver-allow: <reason>'.",
                file=sys.stderr,
            )
            return 1
        print(
            f"config-resolver fragmentation: {len(findings)} site(s)"
            f" (baseline {base.get('finding_count')}) — no growth"
        )
        return 0

    print(f"{len(findings)} fragmented config-read call-site(s)")
    per: dict[str, int] = {}
    for f in findings:
        per[f["name"]] = per.get(f["name"], 0) + 1
    for name, count in sorted(per.items(), key=lambda kv: -kv[1]):
        print(f"  {name}: {count}")
    per_file: dict[str, int] = {}
    for f in findings:
        per_file[f["path"]] = per_file.get(f["path"], 0) + 1
    print("top files:")
    for path, count in sorted(per_file.items(), key=lambda kv: -kv[1])[:15]:
        print(f"  {path}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
