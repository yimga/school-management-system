#!/usr/bin/env python3
"""Insert {# i18n-allow: reason #} above flagged lines from the i18n baseline."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE = REPO_ROOT / "var" / "security-audit-baseline-untranslated-template-text.json"
ALLOW_RE = re.compile(r"{#\s*i18n-allow\s*:")


def reason_for(text: str, tag: str, path: str) -> str | None:
    t = text.strip()
    low = t.lower()
    if "runmycampus" in low or "run my campus" in low:
        return "brand-proper-noun"
    if re.match(r"^alt\s*\+\s*[a-z]$", low):
        return "keyboard-shortcut-hint"
    if path.startswith("templates/admin/partials/admin_v1"):
        return "admin-preview-fixture-path"
    if "/admin/" in t or t.startswith("·") or "?format=json" in t:
        return "admin-preview-fixture-path"
    if tag == "button" and low in {
        "visibility", "undo", "computer", "dark_mode", "light_mode", "filter_list_off"
    }:
        return "material-symbol-ligature"
    if tag == "a" and low in {"add", "key", "logout", "phonelink_erase", "school", "arrow_back"}:
        return "material-symbol-ligature"
    if low in {"add"} and "admin" in path:
        return "material-symbol-ligature"
    return None


def main() -> int:
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    findings = baseline.get("findings") or []
    touched = 0
    by_file: dict[str, list[dict]] = {}
    for f in findings:
        by_file.setdefault(f["path"], []).append(f)
    for rel, file_findings in by_file.items():
        path = REPO_ROOT / rel.replace("\\", "/")
        if not path.is_file():
            continue
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        for f in sorted(file_findings, key=lambda x: x.get("line") or 0, reverse=True):
            line_no = f.get("line")
            if not line_no:
                continue
            why = reason_for(f["text"], f["tag"], rel)
            if not why:
                continue
            idx = line_no - 1
            if idx < 0 or idx >= len(lines):
                continue
            window = "".join(lines[max(0, idx - 1): idx + 1])
            if ALLOW_RE.search(window):
                continue
            indent = re.match(r"\s*", lines[idx]).group(0)
            marker = f"{indent}{{# i18n-allow: {why} #}}\n"
            lines.insert(idx, marker)
            touched += 1
        path.write_text("".join(lines), encoding="utf-8")
    print(f"Inserted {touched} i18n-allow markers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
