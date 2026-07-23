#!/usr/bin/env python
"""Wave N (2026-05-15): documented-baseline drift checker.

Each architectural CI scanner has THREE numbers that should agree:

1. The integer in the **CLAUDE.md scanner table** (hand-maintained docs).
2. The ``finding_count`` in the corresponding
   ``var/security-audit-baseline-<scanner>.json`` (CI gate input).
3. The scanner's **current output** when re-run (the live state).

CI catches #2 vs #3 drift on every PR. But #1 vs #2 drift slips
through silently — see Wave L1a, where CLAUDE.md said 742 long after
the JSON baseline had moved to 734. This script catches that.

Three modes:

* (default) Compare CLAUDE.md doc number to JSON baseline number.
  Exit 1 on any mismatch.
* ``--full`` — additionally re-run each scanner and compare to the
  JSON baseline (the existing CI gate, but bundled here for ops).
* ``--json`` — emit machine-readable output.

Doesn't replace the per-scanner CI jobs; complements them with the
doc-vs-baseline check that nothing else owns today.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
BASELINE_DIR = REPO_ROOT / "var"


# Scanner → JSON baseline filename. Order matches the CLAUDE.md table.
# Filter scripts (no baseline JSON) carry None.
SCANNER_BASELINE_MAP: dict[str, str | None] = {
    "scan_tenant_queryset_safety.py": "security-audit-baseline-tenant-isolation.json",
    "scan_ai_gateway_boundary.py": "security-audit-baseline-ai-gateway-boundary.json",
    "scan_sentry_boundary.py": "security-audit-baseline-sentry-boundary.json",
    "scan_print_statements.py": "security-audit-baseline-print-statements.json",
    "scan_bare_except.py": "security-audit-baseline-bare-except.json",
    "scan_migration_model_imports.py": "security-audit-baseline-migration-model-imports.json",
    "scan_drf_schema_coverage.py": "security-audit-baseline-drf-schema-coverage.json",
    "scan_role_strings.py": "security-audit-baseline-role-strings.json",
    "scan_access_resolver_fragmentation.py": "security-audit-baseline-access-resolver-fragmentation.json",
    "scan_config_resolver_fragmentation.py": "security-audit-baseline-config-resolver-fragmentation.json",
    "scan_granular_rbac_adoption.py": "security-audit-baseline-granular-rbac-adoption.json",
    "scan_upload_validation_coverage.py": "security-audit-baseline-upload-validation-coverage.json",
    "scan_lander_phantom_fields.py": "security-audit-baseline-lander-phantom-fields.json",
    "scan_assert_in_production.py": "security-audit-baseline-assert-in-production.json",
    "scan_magic_numbers.py": "security-audit-baseline-magic-numbers.json",
    "scan_subprocess_shell_true.py": "security-audit-baseline-subprocess-shell.json",
    "scan_inline_style_off_token.py": "security-audit-baseline-inline-style-off-token.json",
    "scan_undefined_css_classes.py": "security-audit-baseline-undefined-css-classes.json",
    "scan_theme_locked_token_text.py": "security-audit-baseline-theme-locked-token-text.json",
    "scan_rls_bypass.py": "security-audit-baseline-rls-bypass.json",
    "scan_money_float.py": "security-audit-baseline-money-float.json",
    "scan_cross_tenancy_fk.py": "security-audit-baseline-cross-tenancy-fk.json",
    "scan_tenant_isolation_marker_quality.py": "security-audit-baseline-tenant-isolation-marker-quality.json",
    "scan_sri_required.py": "security-audit-baseline-sri-required.json",
    "verify_csp_nonce_emission.py": "security-audit-baseline-csp-nonce-emission.json",
    "scan_pwa_manifest_coverage.py": "security-audit-baseline-pwa-manifest-coverage.json",
    # Filters / audit-only scripts that don't produce JSON baselines:
    "audit_template_render_safety.py": None,
    "check_real_migration_drift.py": None,
    "check_documented_baselines.py": None,
    "scan_locale_coverage.py": None,
    "verify_service_worker_version.py": None,
    "verify_slo_registry.py": None,
    "verify_sentry_alert_rule_drift.py": None,
    "verify_dr_drill_schedule.py": None,
}


# Match a CLAUDE.md table row that starts with `| `scanner_name.py` |`.
# Captures the scanner filename and the baseline cell (everything up to
# the next `|`).
_ROW_RE = re.compile(
    r"^\|\s*`(?P<scanner>[\w_]+\.py)`\s*\|\s*(?P<baseline>[^|]+?)\s*\|"
)

# Pull the leading integer out of a baseline cell. Handles formats like:
#   "0", "**0**", "734 (v2.48+L1a; ...)", "**482** (v2.47; ...)", "n/a (filter, ...)"
# Returns None for "n/a"/"none"/etc.
_LEADING_INT_RE = re.compile(r"^\s*\**(?P<n>\d+)\**(?:\s|\(|$)")


@dataclass
class BaselineRow:
    scanner: str
    documented: int | None
    """The integer in CLAUDE.md (None when row says 'n/a' / 'none' / etc.)."""
    json_baseline: int | None
    """``finding_count`` from the JSON baseline file (None when no file)."""
    raw_baseline_text: str
    """Original cell text from CLAUDE.md, for diagnostics."""


def parse_claude_md(path: Path = CLAUDE_MD) -> list[BaselineRow]:
    """Extract baseline rows from CLAUDE.md's scanner table.

    Robust to baseline cells containing pipe characters in code
    spans / backticked strings — the table cells are simple enough
    that we trust the first `|` after the scanner name.
    """
    rows: list[BaselineRow] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _ROW_RE.match(line)
        if not m:
            continue
        scanner = m.group("scanner")
        raw = m.group("baseline").strip()
        # Try to extract a leading integer.
        documented: int | None = None
        if _LEADING_INT_RE.match(raw):
            documented = int(_LEADING_INT_RE.match(raw).group("n"))
        elif raw.lower().startswith(("n/a", "none", "—", "-")):
            documented = None

        # Look up the JSON baseline (independent of doc parse outcome).
        json_count = _read_json_baseline(scanner)

        rows.append(BaselineRow(
            scanner=scanner,
            documented=documented,
            json_baseline=json_count,
            raw_baseline_text=raw,
        ))
    return rows


def _read_json_baseline(scanner: str) -> int | None:
    """Return the baseline finding count for ``scanner``, or None.

    Baselines use a few different schemas across scanners:
      - Most: top-level ``finding_count``.
      - ``scan_undefined_css_classes``: ``total``.
      - ``scan_inline_style_off_token``: ``len(findings)`` (no count).
    Try the keys in priority order and fall back to ``len(findings)``.
    """
    fname = SCANNER_BASELINE_MAP.get(scanner)
    if fname is None:
        return None
    path = BASELINE_DIR / fname
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    for key in ("finding_count", "total"):
        value = data.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    findings = data.get("findings")
    if isinstance(findings, list):
        return len(findings)
    return None


def find_drift(rows: list[BaselineRow]) -> list[tuple[BaselineRow, str]]:
    """Return list of (row, reason) for rows whose doc vs JSON disagree."""
    drift: list[tuple[BaselineRow, str]] = []
    for row in rows:
        # When neither side has a number, nothing to compare.
        if row.documented is None and row.json_baseline is None:
            continue
        # Filter scripts (json_baseline always None) are skipped when
        # the doc also says n/a OR documents the zero-tolerance state.
        if SCANNER_BASELINE_MAP.get(row.scanner) is None:
            # Zero-tolerance gates legitimately document "0" even
            # though they keep no JSON baseline — that's the state
            # they enforce. Only non-zero ints are misleading.
            if row.documented not in (None, 0):
                drift.append((
                    row,
                    f"doc carries integer {row.documented} but scanner "
                    "has no JSON baseline (filter/audit-only).",
                ))
            continue
        # JSON baseline file is expected but missing.
        if row.json_baseline is None:
            drift.append((row, "JSON baseline file missing under var/."))
            continue
        # Doc cell didn't parse as integer.
        if row.documented is None:
            drift.append((
                row,
                f"doc cell is non-numeric but JSON has finding_count "
                f"{row.json_baseline}. Update CLAUDE.md.",
            ))
            continue
        # Both present — compare.
        if row.documented != row.json_baseline:
            drift.append((
                row,
                f"doc says {row.documented}, JSON baseline says "
                f"{row.json_baseline}.",
            ))
    return drift


def _run_scanner(scanner: str) -> int | None:
    """Re-run a scanner and return its current finding_count, or None on failure."""
    script_path = REPO_ROOT / "scripts" / scanner
    if not script_path.exists():
        return None
    try:
        proc = subprocess.run(  # noqa: S603
            [sys.executable, str(script_path), "--json"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode not in (0, 1):
        return None
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None
    count = data.get("finding_count")
    return int(count) if isinstance(count, (int, float)) else None


def _render_text(rows: list[BaselineRow], drift: list, full: bool) -> None:
    print(f"Documented-baseline check: {len(rows)} scanner rows parsed")
    if drift:
        print(f"\nDOC vs JSON drift: {len(drift)}")
        for row, reason in drift:
            print(f"  - {row.scanner}: {reason}")
    else:
        print("  No doc-vs-JSON drift.")
    if full:
        print("\nFull mode: running each scanner against its JSON baseline …")
        for row in rows:
            if SCANNER_BASELINE_MAP.get(row.scanner) is None:
                continue
            current = _run_scanner(row.scanner)
            base = row.json_baseline
            if current is None:
                print(f"  ?  {row.scanner}: could not run scanner")
                continue
            if base is None:
                print(f"  ?  {row.scanner}: no JSON baseline to compare against")
                continue
            if current > base:
                print(
                    f"  !  {row.scanner}: regressed {current} > baseline {base}"
                )
            elif current < base:
                print(
                    f"  v  {row.scanner}: improved {current} < baseline {base} "
                    "(consider lowering baseline)"
                )
            else:
                print(f"  =  {row.scanner}: {current} (matches baseline)")


def _render_json(rows: list[BaselineRow], drift: list, full: bool) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            "CLAUDE.md scanner table integer must equal "
            "var/security-audit-baseline-*.json finding_count"
        ),
        "rows": [
            {
                "scanner": r.scanner,
                "documented": r.documented,
                "json_baseline": r.json_baseline,
                "raw_baseline_text": r.raw_baseline_text,
            }
            for r in rows
        ],
        "drift_count": len(drift),
        "drift": [
            {"scanner": r.scanner, "reason": reason}
            for r, reason in drift
        ],
    }
    if full:
        live = {}
        for row in rows:
            if SCANNER_BASELINE_MAP.get(row.scanner) is None:
                continue
            live[row.scanner] = _run_scanner(row.scanner)
        payload["live_counts"] = live
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full", action="store_true",
        help="Additionally re-run each scanner and compare current to baseline.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit JSON instead of text.",
    )
    args = parser.parse_args()

    rows = parse_claude_md()
    drift = find_drift(rows)

    if args.json:
        _render_json(rows, drift, args.full)
    else:
        _render_text(rows, drift, args.full)

    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
