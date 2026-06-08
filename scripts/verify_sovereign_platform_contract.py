#!/usr/bin/env python3
"""Verify the hardware-sovereign platform architecture contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "config" / "sovereign_platform_contract.json"

ACTIVE_CODE_ROOTS = (
    ROOT / "apps",
    ROOT / "config",
    ROOT / "services",
    ROOT / "templates",
    ROOT / "static" / "js",
)
TEXT_SUFFIXES = {".py", ".html", ".js", ".ts", ".tsx"}


def _load_contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _active_files():
    for base in ACTIVE_CODE_ROOTS:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                yield path


def verify() -> list[str]:
    errors: list[str] = []
    try:
        contract = _load_contract()
    except (OSError, json.JSONDecodeError) as exc:
        return [f"contract unreadable: {exc}"]

    operating_model = contract.get("operating_model") or {}
    for pillar in ("linux", "aws", "salesforce", "shopify", "local"):
        if not str(operating_model.get(pillar) or "").strip():
            errors.append(f"operating model missing pillar: {pillar}")

    for relative in contract.get("forbidden_parallel_architectures") or []:
        if (ROOT / relative).exists():
            errors.append(f"forbidden parallel architecture exists: {relative}")

    forbidden_tokens = tuple(contract.get("forbidden_active_code_tokens") or [])
    for path in _active_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            errors.append(f"cannot read {path.relative_to(ROOT)}: {exc}")
            continue
        for token in forbidden_tokens:
            if token and token in text:
                errors.append(
                    f"forbidden active-code token {token!r}: {path.relative_to(ROOT)}"
                )

    ai_doc = (ROOT / "docs" / "AI_DEPLOYMENT_POSTURE.md").read_text(
        encoding="utf-8", errors="ignore"
    )
    for phrase in (
        "Linux / AWS / Salesforce / Shopify",
        "Hardware support is capability-based",
        "services.ai_helpers",
        "AIEmbeddingStore",
    ):
        if phrase not in ai_doc:
            errors.append(f"AI deployment SOT missing phrase: {phrase}")

    pooling_doc = (ROOT / "docs" / "PGBOUNCER_MULTI_SCHEMA.md").read_text(
        encoding="utf-8", errors="ignore"
    )
    required_pooling = str(contract.get("required_pooling_posture") or "")
    if required_pooling not in pooling_doc:
        errors.append(f"pooling SOT missing required posture: {required_pooling}")
    if "Run PgBouncer in transaction mode" in pooling_doc:
        errors.append("pooling SOT still recommends transaction pooling")

    if "services.ai_gateway" not in str(
        (contract.get("canonical_owners") or {}).get("ai_routing") or ""
    ):
        errors.append("canonical AI owner does not name services.ai_gateway")
    if (contract.get("canonical_owners") or {}).get("tenant_rls_context") != (
        "app.current_school_id"
    ):
        errors.append("canonical RLS context drifted from app.current_school_id")

    return errors


def main() -> int:
    errors = verify()
    if errors:
        print("SOVEREIGN_PLATFORM_CONTRACT_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("SOVEREIGN_PLATFORM_CONTRACT_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
