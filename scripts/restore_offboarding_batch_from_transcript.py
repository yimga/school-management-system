"""Restore operator-only offboarding batch (1753) from agent transcript Write/StrReplace ops."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPT = Path(
    r"C:/Users/yimga/.cursor/projects/c-Users-yimga-Documents-HY-DOC-MAINPC-Docs-for-Others-Friends-family-Gilead-Tech-High-beta-school-management-system/agent-transcripts/64221a81-e398-415a-88fa-f41afbafbe67/64221a81-e398-415a-88fa-f41afbafbe67.jsonl"
)

MARKERS = (
    "offboard",
    "offboarding",
    "switching_pack",
    "parent_gdpr",
    "parent_data_rights",
    "operator_only",
    "1753",
    "purge-certificate",
    "verify-deletion",
    "build_offboarding_exit",
    "offboarding-sla",
    "verify_tenant_offboarding_operator",
    "verify_switching_pack",
)

# Skip unrelated writes that share marker substrings in the same transcript window.
WRITE_SKIP = {
    "apps/billing/stripe_remote_cancel.py",
    "apps/observability/tenant_performance.py",
    "scripts/verify_competitive_gap_closure.py",
}


def _norm_path(path: str) -> str:
    norm = path.replace("\\", "/")
    if "school-management-system/" in norm:
        norm = norm.split("school-management-system/", 1)[1]
    return norm


def _matches(path: str, payload: str) -> bool:
    blob = (path + payload).lower()
    return any(m in blob for m in MARKERS)


def main() -> int:
    if not TRANSCRIPT.is_file():
        print(f"MISSING transcript: {TRANSCRIPT}", file=sys.stderr)
        return 1

    writes: dict[str, str] = {}
    replaces: list[tuple[str, str, str]] = []

    for line in TRANSCRIPT.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        for part in obj.get("message", {}).get("content", []):
            if part.get("type") != "tool_use":
                continue
            name = part.get("name")
            inp = part.get("input", {})
            path = _norm_path(inp.get("path", ""))
            if not path or not _matches(path, json.dumps(inp)):
                continue
            if name == "Write" and inp.get("contents") is not None:
                if path in WRITE_SKIP:
                    continue
                writes[path] = inp["contents"]
            elif name == "StrReplace" and inp.get("old_string") and inp.get("new_string"):
                replaces.append((path, inp["old_string"], inp["new_string"]))

    restored = 0
    for rel, content in sorted(writes.items()):
        dest = ROOT / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8", newline="\n")
        print(f"WRITE {rel}")
        restored += 1

    applied = skipped = 0
    touched: set[str] = set()
    for rel, old, new in replaces:
        dest = ROOT / rel
        if not dest.is_file():
            continue
        text = dest.read_text(encoding="utf-8")
        if old not in text:
            skipped += 1
            continue
        dest.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")
        applied += 1
        touched.add(rel)

    for rel in sorted(touched):
        print(f"PATCH {rel}")

    print(
        f"OK: {restored} writes, {applied} str-replaces applied, {skipped} str-replaces skipped"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
