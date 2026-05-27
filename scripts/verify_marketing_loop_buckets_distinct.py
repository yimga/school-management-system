#!/usr/bin/env python3
"""Each regional loop bucket must have a distinct mp4 fingerprint (not identical copies)."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "docs" / "generated" / "marketing_media_manifest.json"
STATIC = REPO / "static"


def main() -> int:
    if not MANIFEST.is_file():
        print("verify_marketing_loop_buckets_distinct: FAIL — manifest missing", file=sys.stderr)
        return 1
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    digests: dict[str, str] = {}
    errors: list[str] = []
    for bucket, paths in (data.get("loops") or {}).items():
        rel = paths.get("mp4", "")
        p = STATIC / rel
        if not p.is_file():
            errors.append(f"{bucket}: missing {rel}")
            continue
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        if digest in digests.values():
            peer = next(k for k, v in digests.items() if v == digest)
            errors.append(f"{bucket}: identical mp4 to {peer}")
        else:
            digests[bucket] = digest
    if errors:
        print("verify_marketing_loop_buckets_distinct: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"verify_marketing_loop_buckets_distinct: OK ({len(digests)} distinct buckets)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
