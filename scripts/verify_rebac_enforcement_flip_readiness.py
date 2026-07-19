#!/usr/bin/env python3
"""Gate: ReBAC ENFORCE_SENSITIVE flip readiness (artifacts + wiring + SOT codes).

Does NOT flip ``RMC_REBAC_ENFORCE_SENSITIVE`` — that remains an operator env
decision per ``docs/REBAC_ENFORCEMENT_FLIP_RUNBOOK.md``. This gate proves the
repo is flip-*ready*: runbook, pre-flight command, enforce AND-gate tests, and
SENSITIVE_ENFORCED_CODES stay aligned with wired call sites.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "rebac_enforcement_flip_readiness.json"

# Must stay in sync with apps/accounts/rebac_readiness.py::SENSITIVE_ENFORCED_CODES
EXPECTED_CODES = frozenset(
    {"finance.view", "finance.manage", "grade.submit", "attendance.mark"}
)


def _ok(path: str) -> bool:
    return (ROOT / path).is_file()


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _sensitive_codes_from_source() -> set[str]:
    text = _read("apps/accounts/rebac_readiness.py")
    tree = ast.parse(text)
    for node in tree.body:
        value = None
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "SENSITIVE_ENFORCED_CODES":
                    value = node.value
                    break
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "SENSITIVE_ENFORCED_CODES":
                value = node.value
        if value is None or not isinstance(value, ast.Tuple):
            continue
        codes: set[str] = set()
        for elt in value.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                codes.add(elt.value)
            elif isinstance(elt, ast.Str):  # py<3.8 compat
                codes.add(elt.s)
        return codes
    m = re.search(
        r"SENSITIVE_ENFORCED_CODES[^=]*=\s*\((.*?)\)",
        text,
        re.DOTALL,
    )
    if not m:
        return set()
    return set(re.findall(r'"([a-z_.]+)"', m.group(1)))


def _wired_codes() -> set[str]:
    """Codes referenced at known enforce/RebacPermission sites."""
    found: set[str] = set()
    for rel in (
        "apps/finance/api_views.py",
        "apps/api/mobile_api.py",
    ):
        text = _read(rel)
        found.update(re.findall(r'["\'](finance\.(?:view|manage)|grade\.submit|attendance\.mark)["\']', text))
    return found


def main() -> int:
    rows = []
    codes = _sensitive_codes_from_source()
    wired = _wired_codes()

    checks = [
        ("runbook", _ok("docs/REBAC_ENFORCEMENT_FLIP_RUNBOOK.md")),
        (
            "readiness-module",
            _ok("apps/accounts/rebac_readiness.py"),
        ),
        (
            "mgmt-preflight",
            _ok(
                "apps/accounts/management/commands/check_rebac_enforcement_readiness.py"
            ),
        ),
        (
            "enforce-tests",
            _ok("apps/accounts/tests/test_rebac_enforce_sensitive.py"),
        ),
        (
            "readiness-tests",
            _ok("apps/accounts/tests/test_rebac_enforcement_readiness.py"),
        ),
        (
            "settings-flag-default-off",
            'os.getenv("RMC_REBAC_ENFORCE_SENSITIVE", "0")' in _read("config/settings.py"),
        ),
        (
            "sensitive-codes-expected",
            codes == EXPECTED_CODES,
        ),
        (
            "sensitive-codes-wired",
            EXPECTED_CODES.issubset(wired),
        ),
        (
            "enforce_permission_token",
            "def enforce_permission_token" in _read("apps/accounts/rebac.py"),
        ),
    ]

    failed = []
    for name, ok in checks:
        rows.append({"check": name, "ok": bool(ok)})
        if not ok:
            failed.append(name)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ready": not failed,
        "failed": failed,
        "sensitive_codes": sorted(codes),
        "wired_codes_sample": sorted(wired),
        "checks": rows,
        "note": (
            "Flip remains operator-gated via RMC_REBAC_ENFORCE_SENSITIVE=1 after "
            "`manage.py check_rebac_enforcement_readiness` exits 0 on live tenants."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    if failed:
        print(f"REBAC_FLIP_READINESS_FAIL: {', '.join(failed)}")
        print(f"Wrote {OUT}")
        return 1
    print("REBAC_FLIP_READINESS_PASS")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
