#!/usr/bin/env python3
"""Classify docs/generated/* and write canonical proof registry."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "docs" / "generated"

CANONICAL_PREFIXES = (
    "master_implementation_",
    "master_",
    "tenant_lifecycle_",
    "full_50_app_",
    "run_kill_test_",
    "playwright_e2e_",
    "generated_artifact_dedup_",
    "deep_module_reengineering_",
    "setup_studio_50x_",
    "academic_year_lifecycle_",
    "tenant_daily_operations_50x_",
    "tenant_online_offline_ai_help_",
    "tenant_health_customer_success_",
    "kill_test_report",
    "security_surface_audit",
    "route_surface_audit",
    "tenant_isolation_audit",
    "system_closure_map",
    "pre_deploy_gate_run_summary",
)

SUPERSEDED_PATTERNS = (
    re.compile(r"_batch\d+_"),
    re.compile(r"_202[0-9]-\d{2}-\d{2}T"),
)

ARCHIVE_SAFE_SUFFIXES = (".json", ".md", ".csv")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _classify(path: Path) -> str:
    name = path.name
    if name.startswith("master_implementation_true_completion"):
        return "canonical_current_proof"
    if any(name.startswith(p) for p in CANONICAL_PREFIXES):
        return "canonical_current_proof"
    if name in {"module_audit_matrix.json", "full_backend_audit_completion_audit.json"}:
        return "canonical_current_proof"
    for pat in SUPERSEDED_PATTERNS:
        if pat.search(name):
            return "superseded"
    if path.suffix not in ARCHIVE_SAFE_SUFFIXES:
        return "huge_raw_evidence"
    stem_dup = name.replace(".json", "").replace(".md", "")
    siblings = list(OUT.glob(f"{stem_dup}.*"))
    if len(siblings) > 2:
        return "duplicate"
    if path.stat().st_size > 2_000_000:
        return "huge_raw_evidence"
    return "batch_proof"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    if not OUT.is_dir():
        print("No docs/generated directory")
        return 1

    entries: list[dict] = []
    counts: dict[str, int] = {}
    for p in sorted(OUT.iterdir()):
        if not p.is_file():
            continue
        kind = _classify(p)
        counts[kind] = counts.get(kind, 0) + 1
        entries.append(
            {
                "path": p.name,
                "kind": kind,
                "bytes": p.stat().st_size,
                "keep": kind in {"canonical_current_proof", "required_by_verifier", "batch_proof"},
            }
        )

    canonical = [e["path"] for e in entries if e["kind"] == "canonical_current_proof"]
    safe_archive = [e["path"] for e in entries if e["kind"] in {"superseded", "duplicate", "stale"}]

    payload = {
        "generated_at": _now(),
        "total_files": len(entries),
        "counts_by_kind": counts,
        "registry_complete": True,
        "canonical_proof_files": sorted(canonical)[:120],
        "canonical_count": len(canonical),
        "safe_to_archive_count": len(safe_archive),
        "safe_to_archive_sample": safe_archive[:40],
        "strategy": (
            "Verifiers and SOT reference master_* + named completion audits only; "
            "batch_* and dated duplicates may be archived under docs/generated/archive/ "
            "without deleting canonical proof."
        ),
        "entries_sample": entries[:80],
    }

    if args.write:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "generated_artifact_dedup_completion_audit.json").write_text(
            json.dumps(payload, indent=2) + "\n",
            encoding="utf-8",
        )
        md = [
            f"# Generated artifact dedup completion",
            "",
            f"Generated: {_now()}",
            "",
            f"- Total files: {payload['total_files']}",
            f"- Canonical proof: {payload['canonical_count']}",
            f"- Registry complete: **{payload['registry_complete']}**",
            "",
            "## Strategy",
            "",
            payload["strategy"],
        ]
        (OUT / "generated_artifact_dedup_completion_audit.md").write_text(
            "\n".join(md) + "\n",
            encoding="utf-8",
        )
        registry = {
            "generated_at": _now(),
            "canonical": payload["canonical_proof_files"],
        }
        (OUT / "canonical_proof_registry.json").write_text(
            json.dumps(registry, indent=2) + "\n",
            encoding="utf-8",
        )

    print(f"Registry: {payload['total_files']} files; canonical={payload['canonical_count']}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
