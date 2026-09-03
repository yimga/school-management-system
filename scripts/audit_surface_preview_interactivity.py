#!/usr/bin/env python3
"""
Fail when operator/tenant surface-preview mocks use non-interactive spans or readonly fields.

Scoped to cp-section--surface-preview blocks (admin index changelist/changeform demos).
Legitimate readonly elsewhere (share URLs, wizard computed fields) is out of scope.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

SECTION_RE = re.compile(
    r'<section[^>]*cp-section--surface-preview[^>]*>(.*?)</section>',
    re.IGNORECASE | re.DOTALL,
)
FORBIDDEN = [
    (re.compile(r"<span\s+class=\"cp-form__tab\"", re.I), "span.cp-form__tab (use button role=tab)"),
    (re.compile(r"<span\s+class=\"cp-filter-pill\"", re.I), "span.cp-filter-pill (use button)"),
    (
        re.compile(r"<span\s+class=\"cp-pager__pill\"", re.I),
        "span.cp-pager__pill (use button; ellipsis may use span with aria-hidden)",
    ),
    (
        re.compile(r"<input[^>]*class=\"cp-field__input\"[^>]*\sreadonly\b", re.I),
        "readonly cp-field__input in surface preview",
    ),
    (
        re.compile(r"<textarea[^>]*class=\"cp-field__input\"[^>]*\sreadonly\b", re.I),
        "readonly cp-field__textarea in surface preview",
    ),
]
REQUIRED_MARKER = re.compile(r"data-rmc-surface-preview-interactive=", re.I)


def _scan_block(rel: str, block: str, findings: list[dict]) -> None:
    for pattern, issue in FORBIDDEN:
        if pattern.search(block):
            findings.append({"file": rel, "issue": issue, "severity": "high"})
    if not REQUIRED_MARKER.search(block):
        findings.append(
            {
                "file": rel,
                "issue": "missing data-rmc-surface-preview-interactive on preview root",
                "severity": "high",
            }
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    findings: list[dict[str, str]] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if "cp-section--surface-preview" not in text:
            continue
        rel = path.relative_to(ROOT).as_posix()
        if re.search(r"Empty-state example", text, re.I):
            findings.append(
                {
                    "file": rel,
                    "issue": "legacy_empty_state_sidecar_use_nps_metric_card",
                    "severity": "high",
                }
            )
        if "cp-nps-metric" not in text:
            findings.append(
                {
                    "file": rel,
                    "issue": "surface_preview_missing_cp_nps_metric_card",
                    "severity": "medium",
                }
            )
        for block in SECTION_RE.findall(text):
            _scan_block(rel, block, findings)

    payload = {"finding_count": len(findings), "findings": findings}
    out = ROOT / "docs/generated/surface_preview_interactivity_audit.json"
    if args.write:
        out.parent.mkdir(parents=True, exist_ok=True)
        # write_bytes with an explicit \n: Path.write_text is TEXT mode and emits
        # CRLF on Windows, which docs/generated/*.json (eol=lf) then reports as
        # perpetually modified, breaking every rebase.
        out.write_bytes((json.dumps(payload, indent=2) + "\n").encode("utf-8"))

    if args.json:
        print(json.dumps(payload, indent=2))
    elif findings:
        print(
            f"audit_surface_preview_interactivity: {len(findings)} finding(s)",
            file=sys.stderr,
        )
        for f in findings:
            print(f"  [{f['severity']}] {f['file']}: {f['issue']}", file=sys.stderr)
        return 1

    print("audit_surface_preview_interactivity: 0 findings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
