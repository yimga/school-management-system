#!/usr/bin/env python
"""Audit templates for empirically-observable proxies of bad emotional UX.

"Emotional UX confidence" looks subjective, but most of the failure modes are
mechanically detectable. This scanner flags:

  - **Hostile error copy**: bare "Error" / "Invalid input" / "Failed" with no
    helpful next step.
  - **Alarming color without context**: `text-danger` / `bg-danger` adjacent to
    just a status code / number, no explanatory copy.
  - **Naked exception leakage**: templates rendering `{{ exception }}` /
    `{{ traceback }}` / `{{ error.args }}` to operators.
  - **Hostile empty states**: "No records" / "Nothing here" without a
    "{action}" / "next step" affordance.
  - **Imperative commanding tone**: "You must" / "You cannot" without
    explanation — preferred phrasing is reason-first.

Each finding has a severity (`critical` | `warning` | `info`) and a
suggested-fix hint. Output: `docs/generated/emotional_ux_audit.json`.

Exit code: 0 if findings <= baseline; 1 otherwise. Run with `--write-baseline`
to refresh the snapshot after intentional changes.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ROOT = ROOT / "templates"
OUT_PATH = ROOT / "docs" / "generated" / "emotional_ux_audit.json"
BASELINE_PATH = ROOT / "var" / "security-audit-baseline-emotional-ux.json"

ALLOW_MARKER = "ux-allow:"


def _txt(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


HOSTILE_ERROR_RE = re.compile(
    r">\s*(Error|Invalid input|Failed|Bad request|Forbidden|Not allowed)[\s!.:]*<",
    re.I,
)
NAKED_EXCEPTION_RE = re.compile(
    r"\{\{\s*(exception|traceback|err\.args|error\.args|err\.message|exc_info)\b",
    re.I,
)
ALARMING_NUMBER_RE = re.compile(
    r"""class\s*=\s*["'][^"']*\b(text|bg)-danger\b[^"']*["'][^>]*>\s*([0-9]{1,4})\s*<""",
    re.I,
)
HOSTILE_EMPTY_RE = re.compile(
    r">\s*(No (records|results|data|items)( found| yet)?|Nothing here|Empty)[.!\s]*<",
    re.I,
)
IMPERATIVE_TONE_RE = re.compile(
    r"\bYou (must|cannot|may not|are not allowed to|need to)\b",
)
NEXT_STEP_NEARBY_RE = re.compile(
    r"\b(try|click|tap|press|see|review|contact|reach out|reload|retry|adjust|update)\b",
    re.I,
)


def scan(template_root: Path) -> list[dict]:
    findings: list[dict] = []
    for path in sorted(template_root.rglob("*.html")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = str(path.relative_to(ROOT)).replace("\\", "/")
        for ln, raw_line in enumerate(text.splitlines(), 1):
            if ALLOW_MARKER in raw_line:
                continue
            line = raw_line

            if NAKED_EXCEPTION_RE.search(line):
                findings.append(
                    {
                        "file": rel,
                        "line": ln,
                        "severity": "critical",
                        "kind": "naked-exception-leak",
                        "snippet": _txt(line)[:200],
                        "fix": "Replace raw exception render with a controlled message + next step. Log details server-side instead.",
                    }
                )
                continue

            m = HOSTILE_ERROR_RE.search(line)
            if m:
                ctx = text[max(0, text.find(line) - 200): text.find(line) + len(line) + 200]
                if not NEXT_STEP_NEARBY_RE.search(ctx):
                    findings.append(
                        {
                            "file": rel,
                            "line": ln,
                            "severity": "warning",
                            "kind": "hostile-error-copy",
                            "snippet": _txt(line)[:200],
                            "fix": "Add a next-step verb (try, retry, contact, reload). Tell the user what to do next.",
                        }
                    )
                    continue

            m = ALARMING_NUMBER_RE.search(line)
            if m:
                ctx = text[max(0, text.find(line) - 200): text.find(line) + len(line) + 200]
                if not NEXT_STEP_NEARBY_RE.search(ctx):
                    findings.append(
                        {
                            "file": rel,
                            "line": ln,
                            "severity": "info",
                            "kind": "alarming-number-no-context",
                            "snippet": _txt(line)[:200],
                            "fix": "A red number alone reads as scary. Add an aria-label or a small descriptor (e.g., 'overdue this term').",
                        }
                    )
                    continue

            m = HOSTILE_EMPTY_RE.search(line)
            if m:
                ctx = text[max(0, text.find(line) - 400): text.find(line) + len(line) + 400]
                if not NEXT_STEP_NEARBY_RE.search(ctx):
                    findings.append(
                        {
                            "file": rel,
                            "line": ln,
                            "severity": "info",
                            "kind": "hostile-empty-state",
                            "snippet": _txt(line)[:200],
                            "fix": "Empty states should suggest the next move ('Add your first student', 'Invite a parent').",
                        }
                    )
                    continue

            m = IMPERATIVE_TONE_RE.search(line)
            if m:
                snippet_after = line[m.end(): m.end() + 240]
                if not re.search(r"\bbecause\b|\bsince\b|\bso that\b|—", snippet_after, re.I):
                    findings.append(
                        {
                            "file": rel,
                            "line": ln,
                            "severity": "info",
                            "kind": "imperative-tone-no-reason",
                            "snippet": _txt(line)[:200],
                            "fix": "Lead with the reason ('To protect parent data, …') instead of the prohibition.",
                        }
                    )
    return findings


def load_baseline() -> int:
    if not BASELINE_PATH.exists():
        return 0
    try:
        data = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        return int(data.get("finding_count", 0))
    except (json.JSONDecodeError, ValueError):
        return 0


def write_baseline(count: int) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(
            {"finding_count": count, "updated_at": datetime.now(timezone.utc).isoformat()},
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()

    findings = scan(TEMPLATE_ROOT)
    by_kind: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for f in findings:
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1
        by_severity[f["severity"]] = by_severity.get(f["severity"], 0) + 1
    total = len(findings)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "finding_count": total,
                "by_kind": by_kind,
                "by_severity": by_severity,
                "findings": findings,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"Emotional UX findings: {total}  by_severity={by_severity}  by_kind={by_kind}")
    if args.summary_only:
        return 0

    if args.write_baseline:
        write_baseline(total)
        print(f"Baseline written: {total}")
        return 0

    baseline = load_baseline()
    if total > baseline:
        print(
            f"FAIL: {total} > baseline {baseline}. New emotional UX regressions. "
            f"Fix them, or mark intentional copy with `<!-- ux-allow: <reason> -->`, "
            f"or run `python scripts/audit_emotional_ux_signals.py --write-baseline` "
            f"to acknowledge the new floor."
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
