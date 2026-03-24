#!/usr/bin/env python3
"""
Merge classified CSRF-exempt, AllowAny, and raw-SQL allowlists into one machine-readable
ledger for Phase 8 (security / trust / endpoint hardening).

Source of truth remains the three allowlist JSON files; this artifact is a denormalized
view for auditors and CI drift detection.

Usage:
  python scripts/build_phase8_security_ledger.py --write   # refresh scripts/generated/
  python scripts/build_phase8_security_ledger.py --check   # fail if file stale (CI)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_REL = Path("scripts/generated/phase8_security_ledger.json")
CSRF = ROOT / "scripts/allowlists/csrf_exempt_allowlist.json"
ALLOW_ANY = ROOT / "scripts/allowlists/allow_any_allowlist.json"
RAW_SQL = ROOT / "scripts/allowlists/raw_sql_allowlist.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _build() -> dict:
    csrf = _load(CSRF)
    allow_any = _load(ALLOW_ANY)
    raw_sql = _load(RAW_SQL)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {
            "csrf_exempt_allowlist": "scripts/allowlists/csrf_exempt_allowlist.json",
            "allow_any_allowlist": "scripts/allowlists/allow_any_allowlist.json",
            "raw_sql_allowlist": "scripts/allowlists/raw_sql_allowlist.json",
        },
        "summary": {
            "csrf_exempt_files": len(csrf.get("files", {})),
            "allow_any_files": len(allow_any.get("files", {})),
            "raw_sql_files": len(raw_sql.get("files", {})),
        },
        "csrf_exempt": csrf.get("files", {}),
        "allow_any": allow_any.get("files", {}),
        "raw_sql": raw_sql.get("files", {}),
    }


def _canonical_json(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, indent=2).encode("utf-8") + b"\n"


def _fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Phase 8 merged security ledger.")
    parser.add_argument(
        "--write", action="store_true", help="Write scripts/generated/phase8_security_ledger.json"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if generated file does not match current allowlists",
    )
    args = parser.parse_args()
    if not args.write and not args.check:
        print("Specify --write and/or --check", file=sys.stderr)
        return 2

    for p in (CSRF, ALLOW_ANY, RAW_SQL):
        if not p.is_file():
            print(f"Missing source: {p}", file=sys.stderr)
            return 1

    payload = _build()
    body = _canonical_json(payload)
    out_path = ROOT / OUT_REL

    if args.write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(body)
        print(f"Wrote {OUT_REL} ({len(body)} bytes) sha256={_fingerprint(body)[:16]}…")

    if args.check:
        if not out_path.is_file():
            print(f"FAIL: {OUT_REL} missing; run with --write", file=sys.stderr)
            return 1
        on_disk_obj = json.loads(out_path.read_text(encoding="utf-8"))
        fresh_obj = json.loads(body.decode("utf-8"))
        # generated_at changes every run; drift detection is on allowlist content only.
        on_disk_obj.pop("generated_at", None)
        fresh_obj.pop("generated_at", None)
        if on_disk_obj != fresh_obj:
            print(
                "FAIL: phase8_security_ledger.json is stale. Run:\n"
                "  python scripts/build_phase8_security_ledger.py --write",
                file=sys.stderr,
            )
            return 1
        print("OK   phase8_security_ledger.json matches allowlists")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
