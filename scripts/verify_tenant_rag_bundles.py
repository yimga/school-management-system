#!/usr/bin/env python3
"""Phase P3 gate for portable, signed, single-store tenant RAG bundles."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    service = (ROOT / "services" / "tenant_rag_bundle.py").read_text(
        encoding="utf-8"
    )
    for token in (
        "rmc.tenant-rag-bundle.v1",
        "HMAC-SHA256",
        "body_sha256",
        "Bundle tenant binding does not match import target.",
        "newer_tombstone",
        "MAX_BUNDLE_RECORDS",
        "@transaction.atomic",
    ):
        if token not in service:
            errors.append(f"bundle contract missing: {token}")

    model = (ROOT / "apps" / "siteconfig" / "models_ai.py").read_text(
        encoding="utf-8"
    )
    for token in (
        "document_id",
        "embedding_model",
        "embedding_dimensions",
        "lifecycle_status",
        "retention_until",
        "source_updated_at",
    ):
        if token not in model:
            errors.append(f"canonical embedding lifecycle field missing: {token}")

    memory = (ROOT / "services" / "ai_memory.py").read_text(encoding="utf-8")
    for token in (
        'lifecycle_status="active"',
        "retention_until__gt=timezone.now()",
        'Q(embedding_model="") | Q(embedding_model=model_id)',
    ):
        if token not in memory:
            errors.append(f"retrieval safety filter missing: {token}")

    for forbidden in ("sqlite_vec", "sqlite-vec", "LWW-Element-Set"):
        if forbidden in service:
            errors.append(f"unapproved secondary truth-store mechanism: {forbidden}")

    commands = [
        [
            sys.executable,
            "scripts/run_sqlite_memory_tests.py",
            "services.tests.test_tenant_rag_bundle",
            "services.tests.test_ai_memory",
            "--verbosity=1",
        ],
        [
            sys.executable,
            "scripts/run_sqlite_memory_tests.py",
            "apps.analytics.tests.test_ai_surfaces",
            "apps.analytics.tests.test_wave9_language_pgvector",
            "apps.analytics.tests.test_pgvector_production",
            "--verbosity=1",
        ],
        [sys.executable, "manage.py", "makemigrations", "--check", "--dry-run"],
    ]
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode:
            errors.append(f"verification command failed: {' '.join(command)}")

    if errors:
        print("TENANT_RAG_BUNDLE_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("TENANT_RAG_BUNDLE_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
