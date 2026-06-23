#!/usr/bin/env python3
"""Zero-tolerance gate: Cameroon currency fallback locks in tenant/runtime code.

Flags ``or "XAF"`` / ``or 'XAF'`` used as a last-resort currency when tenant context
is missing. Country/regional catalog maps (``CM → XAF``) are allowlisted; tenant
money must fall back to ``PLATFORM_DEFAULT_CURRENCY``, not XAF.

Mark intentional sites with ``# currency-fallback-allow: <reason>`` on the same line
or the line above.

Run:
  python scripts/scan_currency_tenant_fallback.py
  python scripts/scan_currency_tenant_fallback.py --compare
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-currency-tenant-fallback.json"

SCAN_ROOTS = (
    REPO_ROOT / "apps",
    REPO_ROOT / "services",
    REPO_ROOT / "payment",
)

SKIP_DIR_NAMES = {
    "migrations",
    "tests",
    "node_modules",
    "__pycache__",
    ".git",
}

ALLOW_PREFIXES = (
    "apps/siteconfig/localization_context_processor.py",
    "apps/siteconfig/tenant_config.py",
    "apps/siteconfig/translations.py",
    "apps/siteconfig/local_experience_profiles.py",
    "apps/siteconfig/geoip_service.py",
    "apps/schools/marketing_geo_context.py",
    "apps/billing/psp_adapter_registry.py",
    "apps/billing/regional_pricing.py",
    "apps/metadata/country_eav_catalog.py",
)

ALLOW_MARKER = "currency-fallback-allow:"
PATTERN = re.compile(r"""or\s+['"]XAF['"]""")


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _allowed_path(rel: str) -> bool:
    return any(rel == prefix or rel.startswith(prefix.replace(".py", "/")) for prefix in ALLOW_PREFIXES)


def _has_allow_marker(lines: list[str], line_no: int) -> bool:
    for idx in (line_no - 1, line_no - 2):
        if 0 <= idx < len(lines) and ALLOW_MARKER in lines[idx]:
            return True
    return False


def scan() -> list[dict[str, str | int]]:
    findings: list[dict[str, str | int]] = []
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            rel = _rel(path)
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if _allowed_path(rel):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            lines = text.splitlines()
            for line_no, line in enumerate(lines, start=1):
                if PATTERN.search(line) and not _has_allow_marker(lines, line_no):
                    findings.append(
                        {
                            "path": rel,
                            "line": line_no,
                            "snippet": line.strip()[:160],
                        }
                    )
    findings.sort(key=lambda item: (str(item["path"]), int(item["line"])))
    return findings


def _load_baseline() -> dict:
    if not BASELINE_PATH.is_file():
        return {"finding_count": 0, "findings": [], "generated_at": None}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true", help="Fail when findings != baseline")
    parser.add_argument("--write-baseline", action="store_true", help="Rewrite baseline JSON")
    args = parser.parse_args(argv)

    findings = scan()
    count = len(findings)

    if args.write_baseline:
        payload = {
            "finding_count": count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "findings": findings,
        }
        BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote baseline: {count} finding(s) -> {BASELINE_PATH.relative_to(REPO_ROOT)}")
        return 0

    if args.compare:
        baseline = _load_baseline()
        expected = int(baseline.get("finding_count", 0))
        if count != expected:
            print(
                f"CURRENCY_TENANT_FALLBACK_FAIL: {count} finding(s), baseline {expected}",
                file=sys.stderr,
            )
            for item in findings[:20]:
                print(f"  {item['path']}:{item['line']}  {item['snippet']}", file=sys.stderr)
            if count > 20:
                print(f"  … and {count - 20} more", file=sys.stderr)
            return 1
        print(f"CURRENCY_TENANT_FALLBACK_PASS ({count} finding(s), baseline {expected})")
        return 0

    print(f"currency-tenant-fallback: {count} finding(s)")
    for item in findings:
        print(f"  {item['path']}:{item['line']}  {item['snippet']}")
    return 0 if count == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
