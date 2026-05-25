#!/usr/bin/env python3
"""Revalidation audit for dual-plane identity & access (operator + tenant)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GENERATED = ROOT / "docs" / "generated" / "identity_access_revalidation_audit.json"


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _run(script: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / script)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=1200,
    )
    out = ((proc.stdout or "") + (proc.stderr or "")).strip()
    token = ""
    for line in out.splitlines():
        if line.endswith("_PASS") or line.endswith("_FAIL"):
            token = line.strip()
    return proc.returncode == 0, token or out[-400:]


def main() -> int:
    rows: list[dict] = []

    def add(check_id: str, ok: bool, proof: str) -> None:
        rows.append({"check_id": check_id, "ok": ok, "proof": proof})

    add(
        "operator-verifier",
        *_run("verify_operator_identity_hub.py"),
    )
    add(
        "tenant-verifier",
        *_run("verify_tenant_identity_hub.py"),
    )
    add(
        "completion-gate",
        *_run("verify_identity_access_completion.py"),
    )
    add(
        "makemigrations-accounts",
        subprocess.run(
            [sys.executable, "manage.py", "makemigrations", "accounts", "--check", "--dry-run"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        ).returncode == 0,
        "accounts makemigrations --check",
    )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finding_count": sum(1 for r in rows if not r["ok"]),
        "rows": rows,
    }
    GENERATED.parent.mkdir(parents=True, exist_ok=True)
    GENERATED.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if payload["finding_count"]:
        print("IDENTITY_ACCESS_REVALIDATION_FAIL")
        for r in rows:
            if not r["ok"]:
                print(f"  FAIL {r['check_id']}: {r['proof'][:200]}")
        return 1
    print("IDENTITY_ACCESS_REVALIDATION_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
