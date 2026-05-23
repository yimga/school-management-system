#!/usr/bin/env python3
"""SODP offline auth contract gate."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    findings: list[str] = []
    for rel in (
        "apps/accounts/models_offline_device.py",
        "apps/api/offline_device_api.py",
        "static/js/rmc-offline-auth-vault.js",
        "apps/accounts/migrations/0034_sodp_offline_waves.py",
    ):
        if not (ROOT / rel).is_file():
            findings.append(f"missing {rel}")

    vault = (ROOT / "static/js/rmc-offline-auth-vault.js").read_text(encoding="utf-8", errors="replace")
    for needle in ("PBKDF2", "AES-GCM", "localStorage"):
        if needle not in vault:
            findings.append(f"rmc-offline-auth-vault missing {needle}")
    if re.search(r"password_hash|argon2", vault, re.I):
        findings.append("vault must not store password hashes")

    api = (ROOT / "apps/api/offline_device_api.py").read_text(encoding="utf-8", errors="replace")
    if "csrf_exempt" in api:
        findings.append("offline token API must not be csrf_exempt")
    if "@extend_schema" not in api:
        findings.append("OfflineTokenMintView missing @extend_schema")

    lib = (ROOT / "companion-tauri/src-tauri/src/lib.rs").read_text(encoding="utf-8", errors="replace")
    if "rmc_stronghold_seal" not in lib or "rmc_stronghold_open" not in lib:
        findings.append("companion-tauri missing Stronghold stub commands")

    if findings:
        print("verify_offline_auth_contract: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1
    print("verify_offline_auth_contract: OFFLINE_AUTH_CONTRACT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
