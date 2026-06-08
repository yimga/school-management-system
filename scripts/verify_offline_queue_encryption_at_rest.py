#!/usr/bin/env python3
"""Repo gate: offline queue AES-GCM at rest wiring (batch 1651)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _text(rel: str) -> str:
    p = ROOT / rel
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""


def main() -> int:
    findings: list[str] = []

    sw = _text("static/js/service-worker.js")
    crypto_js = _text("static/js/rmc-offline-queue-crypto.js")
    bootstrap = _text("static/js/rmc-offline-encryption-bootstrap.js")
    platform = _text("apps/siteconfig/platform_surface_config.py")
    bundle = _text("apps/platform_runtime/offline_mode_bundle.py")

    if "rmc-offline-queue-crypto.js" not in sw:
        findings.append("service-worker missing importScripts for queue crypto")
    if "RmcOfflineQueueCrypto" not in sw or "rmc-aes-gcm:v1:" not in crypto_js:
        findings.append("AES-GCM crypto helper missing or incomplete")
    if "encryptionKeyUrl" not in platform or "encryptOutbox" not in platform:
        findings.append("platform_surface_config missing encryptionKeyUrl / encryptOutbox")
    if "enable_offline_queue_encryption" not in bundle:
        findings.append("offline_mode_bundle missing enable_offline_queue_encryption")
    if "encryption-key" not in _text("apps/api/urls.py"):
        findings.append("api urls missing offline encryption-key route")
    if "rmc-offline-encryption-bootstrap.js" not in _text(
        "templates/partials/rmc_sms_offline_config.html"
    ):
        findings.append("sms offline config partial missing encryption bootstrap")
    if "rmc-offline-config-ready" not in bootstrap:
        findings.append("encryption bootstrap missing ready event")

    if findings:
        for f in findings:
            print(f"FAIL: {f}")
        return 1

    print("OFFLINE_QUEUE_ENCRYPTION_AT_REST_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
