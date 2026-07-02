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
    if "RMC_OFFLINE_CAPABILITY_TOKEN_TTL_HOURS" not in api:
        findings.append("mint TTL must be settings-driven (RMC_OFFLINE_CAPABILITY_TOKEN_TTL_HOURS)")
    if re.search(r"timedelta\(hours=\d+\)", api):
        findings.append("mint TTL must not be a hardcoded timedelta literal")

    # Revocation governance (shipped 2026-07-02): both registration paths used
    # to hard-set revoked_at: None in update_or_create defaults, so a revoked
    # (stolen) device silently un-revoked itself by re-minting. Lock the
    # boundary on BOTH paths: no reset, and an explicit revoked-device refusal.
    queue = (ROOT / "apps/platform_runtime/offline_queue.py").read_text(
        encoding="utf-8", errors="replace"
    )
    for label, text in (("offline_device_api", api), ("offline_queue signup", queue)):
        if re.search(r"[\"']revoked_at[\"']\s*:\s*None", text):
            findings.append(f"{label} must not reset revoked_at at registration (revocation defeat)")
        if "device_revoked" not in text:
            findings.append(f"{label} must refuse revoked devices with a device_revoked error")
    gov_path = ROOT / "apps/portal/views_device_governance.py"
    if not gov_path.is_file():
        findings.append("missing apps/portal/views_device_governance.py (operator revoke surface)")
    else:
        gov = gov_path.read_text(encoding="utf-8", errors="replace")
        if "OfflineCapabilityToken" not in gov or "update(revoked_at" not in gov:
            findings.append("device revoke must cascade to outstanding capability tokens")

    # Client<->server mint contract (the refresh shipped broken for months:
    # no device_id -> 400, no CSRF header -> 403, and it read a response field
    # the server never returned). Lock the wire contract on both sides.
    bootstrap_path = ROOT / "static/js/rmc-offline-auth-bootstrap.js"
    if not bootstrap_path.is_file():
        findings.append("missing static/js/rmc-offline-auth-bootstrap.js")
    else:
        bootstrap = bootstrap_path.read_text(encoding="utf-8", errors="replace")
        if "device_id: deviceId" not in bootstrap:
            findings.append("bootstrap mint POST must send device_id (serializer requires it)")
        if "X-CSRFToken" not in bootstrap:
            findings.append("bootstrap mint POST must send X-CSRFToken (SessionAuthentication enforces CSRF)")
        if "capability_blob_b64" in bootstrap:
            findings.append("bootstrap reads capability_blob_b64 — the server returns capability_blob")
        if "data.capability_blob" not in bootstrap:
            findings.append("bootstrap must read capability_blob from the mint response")
        if "applyMintResponse" not in bootstrap:
            findings.append("bootstrap must apply the minted iam_snapshot via RMCIamSnapshot.applyMintResponse")

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
