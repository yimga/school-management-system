#!/usr/bin/env python3
"""IAM identity 10x gate — scopes, posture enforcement, PDP wiring, seeding."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "generated" / "iam_identity_10x_audit.json"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _run(script: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=900,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    token = ""
    for line in out.splitlines():
        if line.endswith("_PASS") or line.endswith("_FAIL"):
            token = line.strip()
    return proc.returncode == 0, token or out[-300:]


def _super_scope_coverage_ratio() -> tuple[float, int, int]:
    schools = ROOT / "apps" / "schools"
    total = 0
    scoped = 0
    for path in schools.glob("super_views*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"^def (super_\w+|api_\w+)\(", text, re.MULTILINE):
            total += 1
            start = m.start()
            prefix = text[max(0, start - 400) : start]
            if "@require_platform_scope(" in prefix:
                scoped += 1
    return (scoped / total if total else 1.0, scoped, total)


def main() -> int:
    rows: list[dict] = []

    def add(cid: str, ok: bool, proof: str) -> None:
        rows.append({"check_id": cid, "ok": ok, "proof": proof})

    settings = _read("config/settings.py")
    add(
        "minimum-strength-middleware",
        "MinimumSecurityStrengthMiddleware" in settings,
        "settings MIDDLEWARE",
    )
    add(
        "security-minimum-settings",
        "SECURITY_PLATFORM_MINIMUM_SCORE" in settings
        and "SECURITY_ENFORCE_MINIMUM_STRENGTH" in settings,
        "minimum score env",
    )
    add(
        "rbac-pdp-wired",
        "rbac_dashboard_pdp" in _read("apps/accounts/views.py"),
        "rbac PDP decorator",
    )
    add(
        "tenant-pdp-wired",
        "tenant_identity_hub_pdp" in _read("apps/accounts/views_tenant_identity.py"),
        "tenant identity PDP",
    )
    add(
        "operator-seed-command",
        (ROOT / "apps/accounts/management/commands/ensure_platform_operator_profiles.py").is_file(),
        "ensure_platform_operator_profiles",
    )
    add(
        "tenant-demo-seed-command",
        (ROOT / "apps/accounts/management/commands/seed_tenant_identity_demo.py").is_file(),
        "seed_tenant_identity_demo",
    )
    add(
        "permission-manifest-v1",
        (ROOT / "apps/accounts/permission_manifest.py").is_file(),
        "colon token manifest",
    )
    add(
        "rebac-offline-slice",
        (ROOT / "apps/accounts/rebac.py").is_file()
        and (ROOT / "apps/accounts/iam_snapshot.py").is_file(),
        "batch 1507 rebac + snapshot",
    )
    ratio, scoped, total = _super_scope_coverage_ratio()
    add(
        "super-scope-coverage-80pct",
        ratio >= 0.80,
        f"{scoped}/{total} handlers scoped ({ratio:.0%})",
    )
    add("batch-1505-audit", *_run("audit_batch_1505_completeness.py"))
    add("scope-verifier", *_run("verify_super_platform_scope_coverage.py"))
    matrix = _read("scripts/audit_role_permission_matrix.py")
    add(
        "matrix-knows-platform-scope",
        "require_platform_scope" in matrix,
        "audit_role_permission_matrix",
    )

    finding = sum(1 for r in rows if not r["ok"])
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finding_count": finding,
        "super_scope_ratio": ratio,
        "super_scope_scoped": scoped,
        "super_scope_total": total,
        "rows": rows,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if finding:
        print("IAM_IDENTITY_10X_FAIL")
        for r in rows:
            if not r["ok"]:
                print(f"  {r['check_id']}: {r['proof'][:160]}")
        return 1
    print("IAM_IDENTITY_10X_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
