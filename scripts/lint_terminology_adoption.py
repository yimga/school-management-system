#!/usr/bin/env python3
"""Terminology-adoption drift detector for tenant-facing templates.

Flags hardcoded canonical lexicon defaults (e.g. bare "Student", "Teacher",
"Sequence") in Django templates that should route through ``{% term %}`` /
``{% trans_term %}`` so tenant overrides win.

Drift-detection only: baseline records the current count; CI trips on NEW
findings. Mark intentional sites with ``<!-- terminology-adopt-allow: <reason> -->``
on the same line or the line above.

Run:
  python scripts/lint_terminology_adoption.py
  python scripts/lint_terminology_adoption.py --compare
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = REPO_ROOT / "templates"
BASELINE_PATH = REPO_ROOT / "var" / "security-audit-baseline-terminology-adoption.json"

ALLOW_MARKER = "terminology-adopt-allow:"

# Operator/config surfaces where literal English defaults are expected.
EXCLUDED_PREFIXES = (
    "templates/marketing/",
    "templates/admin/",
    "templates/emails/",
    "templates/siteconfig/partials/lexicon_",
    "templates/siteconfig/feature_control",
)

# Lines using these adoption surfaces are skipped.
ADOPTION_MARKERS = (
    "{% term ",
    "{% trans_term ",
    "{% grade_label",
    "{% gpa_label",
    "{% term_label",
    "{% report_label",
    "{% trans ",
    "{% blocktrans ",
)

# Skip attribute-ish lines (class names, URLs, IDs) to reduce noise.
_ATTR_HINT = re.compile(
    r"""(?ix)
    \bclass=|\bid=|\bhref=|\bsrc=|\bdata-[a-z-]+=
    |\burl\s*['"]|\bstatic\s+['"]
    """
)

_TAG_RE = re.compile(r"\{%[^%]*%\}")
_VAR_RE = re.compile(r"\{\{[^}]*\}\}")
_COMMENT_RE = re.compile(r"\{#.*?#\}", re.DOTALL)


def _load_lexicon_terms() -> list[tuple[str, str, str]]:
    sys.path.insert(0, str(REPO_ROOT))
    from apps.siteconfig.lexicon_catalog import LEXICON_REGISTRY

    terms: list[tuple[str, str, str]] = []
    for key, (sing, plur, _cat, _desc) in LEXICON_REGISTRY.items():
        for label in (sing, plur):
            label = (label or "").strip()
            if len(label) >= 4:
                terms.append((key, label, label.lower()))
    # Longest labels first so "Head teacher" matches before "Teacher".
    terms.sort(key=lambda item: len(item[1]), reverse=True)
    return terms


def _is_excluded(rel_posix: str) -> bool:
    return rel_posix.startswith(EXCLUDED_PREFIXES)


def _is_allowlisted(lines: list[str], lineno: int) -> bool:
    for offset in (0, -1):
        idx = lineno - 1 + offset
        if 0 <= idx < len(lines) and ALLOW_MARKER in lines[idx]:
            return True
    return False


def _line_uses_adoption_surface(line: str) -> bool:
    return any(marker in line for marker in ADOPTION_MARKERS)


def _scan_template(path: Path, lexicon: list[tuple[str, str, str]]) -> list[dict]:
    rel = path.relative_to(REPO_ROOT).as_posix()
    if _is_excluded(rel):
        return []
    raw = path.read_text(encoding="utf-8", errors="replace")
    raw = _COMMENT_RE.sub("", raw)
    lines = raw.splitlines()
    findings: list[dict] = []
    compiled = [
        (key, label, re.compile(rf"(?<![A-Za-z0-9_]){re.escape(label)}(?![A-Za-z0-9_])", re.I))
        for key, label, _lower in lexicon
    ]
    for lineno, line in enumerate(lines, start=1):
        if _is_allowlisted(lines, lineno):
            continue
        if _line_uses_adoption_surface(line):
            continue
        if _ATTR_HINT.search(line):
            continue
        scrubbed = _TAG_RE.sub(" ", line)
        scrubbed = _VAR_RE.sub(" ", scrubbed)
        if not scrubbed.strip():
            continue
        for key, label, pattern in compiled:
            if pattern.search(scrubbed):
                findings.append(
                    {
                        "path": rel,
                        "line": lineno,
                        "key": key,
                        "literal": label,
                    }
                )
                break
    return findings


def _scan() -> list[dict]:
    lexicon = _load_lexicon_terms()
    findings: list[dict] = []
    if not TEMPLATES_DIR.exists():
        return findings
    for path in sorted(TEMPLATES_DIR.rglob("*.html")):
        findings.extend(_scan_template(path, lexicon))
    findings.sort(key=lambda item: (item["path"], item["line"], item["key"]))
    return findings


def _baseline_payload(findings: list[dict]) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rule": (
            "Tenant-facing templates must not hardcode canonical lexicon defaults; "
            "use {% term %} / {% trans_term %} / legacy *_label tags."
        ),
        "scan_root": TEMPLATES_DIR.relative_to(REPO_ROOT).as_posix(),
        "excluded_prefixes": list(EXCLUDED_PREFIXES),
        "allow_marker": ALLOW_MARKER,
        "finding_count": len(findings),
        "findings": findings,
    }


def _load_baseline() -> dict | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _print_summary(findings: list[dict]) -> None:
    print(f"Terminology-adoption scan: {len(findings)} hardcoded canonical literal(s)")
    for item in findings[:40]:
        print(
            f"  {item['path']}:{item['line']}  key={item['key']}  literal={item['literal']!r}"
        )
    if len(findings) > 40:
        print(f"  ... and {len(findings) - 40} more (see --json)")


def _write_baseline(findings: list[dict]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(_baseline_payload(findings), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"  wrote baseline -> {BASELINE_PATH.relative_to(REPO_ROOT)}")


def _compare(findings: list[dict]) -> int:
    baseline = _load_baseline()
    if baseline is None:
        _print_summary(findings)
        print("\nNo baseline on disk. Run without --compare to write one.")
        return 1 if findings else 0
    baseline_counts = Counter(
        (item["path"], item["key"], item["literal"]) for item in baseline.get("findings", [])
    )
    current_counts = Counter(
        (item["path"], item["key"], item["literal"]) for item in findings
    )
    new = current_counts - baseline_counts
    removed = baseline_counts - current_counts
    _print_summary(findings)
    if new:
        print("\nNEW hardcoded terminology literal(s) introduced:")
        for (path, key, literal), count in sorted(new.items()):
            print(f"  {path}  key={key} literal={literal!r}  +{count}")
    if removed:
        print("\nRemoved (consider updating baseline):")
        for (path, key, literal), count in sorted(removed.items()):
            print(f"  {path}  key={key} literal={literal!r}  -{count}")
    return 1 if new else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = _scan()
    if args.json:
        print(json.dumps(_baseline_payload(findings), indent=2, sort_keys=True))
        return 0
    if args.compare:
        return _compare(findings)
    _print_summary(findings)
    _write_baseline(findings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
