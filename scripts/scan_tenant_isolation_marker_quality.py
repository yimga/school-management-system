#!/usr/bin/env python
"""Tenant-isolation marker REASON-QUALITY gate.

12-pillar audit P3 follow-up. Sister to
``scripts/scan_tenant_queryset_safety.py`` (which counts how many
queries are allowlisted) and ``scripts/verify_tenant_scoping_burndown.py``
(which enforces the quarterly schedule for reducing that count).

This scanner reads the **reason string** that a developer wrote after
``# tenant-isolation-allow:`` and flags reason strings that look lazy:

* Empty reason (``# tenant-isolation-allow:`` with nothing after the colon).
* Single-word placeholders that don't actually explain why
  (``TODO``, ``FIXME``, ``XXX``, ``HACK``, ``WIP``, ``later``, ``unknown``).
* Multi-word placeholders that promise to fix it but aren't a reason
  (``fix later``, ``see above``, ``see below``, ``revisit``, ``check``,
  ``temporary``, ``temp``).
* Reasons under 8 characters (no plausibly-real reason fits in that long).
* Reasons that don't contain at least two whitespace-separated tokens
  (a single hyphenated string like ``cross-tenant`` is allowed because
  we use a lot of compound markers like
  ``view-layer-scoped-via-request-school-or-role-graph``).

The forward-progress verifier alone cannot detect any of these — by
definition, every site it counts already passed the literal regex
``# tenant-isolation-allow:``. This scanner is the lazy-marker gate.

Modes:

* Default: prints findings, exits 0 (informational).
* ``--compare``: compare against
  ``var/security-audit-baseline-tenant-isolation-marker-quality.json``;
  exit 1 when the count grows (zero-tolerance-from-day-N).
* ``--write-baseline``: capture current state into the baseline JSON.
* ``--json``: machine-readable.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import tokenize
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = (
    REPO_ROOT
    / "var"
    / "security-audit-baseline-tenant-isolation-marker-quality.json"
)
SEARCH_ROOTS = [REPO_ROOT / "apps", REPO_ROOT / "services", REPO_ROOT / "config"]

# Match the marker and capture the reason string (everything after the colon
# to end of line). Whitespace between the comment hash and the literal is
# tolerated so we also catch end-of-line trailing markers.
_MARKER_RE = re.compile(
    r"#\s*tenant-isolation-allow:\s*(?P<reason>.*?)\s*$"
)

# Words / phrases that are placeholders, not reasons. Lowercased.
_LAZY_WORDS: frozenset[str] = frozenset(
    {
        "todo",
        "fixme",
        "xxx",
        "hack",
        "wip",
        "later",
        "unknown",
        "n/a",
        "tbd",
        "?",
        "??",
        "???",
    }
)
_LAZY_PHRASES: tuple[str, ...] = (
    "fix later",
    "fix-later",
    "see above",
    "see-above",
    "see below",
    "see-below",
    "revisit",
    "check this",
    "check later",
    "temporary",
    "temp marker",
    "for now",
    "placeholder",
    "do not know",
    "i dont know",
    "not sure",
)


@dataclass(frozen=True)
class Finding:
    path: str
    lineno: int
    reason: str
    kind: str  # empty / single-word-lazy / phrase-lazy / too-short / one-token


def _classify(reason: str) -> str | None:
    stripped = reason.strip()
    if not stripped:
        return "empty"

    lowered = stripped.lower()
    if lowered in _LAZY_WORDS:
        return "single-word-lazy"

    for phrase in _LAZY_PHRASES:
        if phrase in lowered:
            return "phrase-lazy"

    if len(stripped) < 8:
        return "too-short"

    # Real reasons usually have at least 2 whitespace tokens OR are a
    # plausibly-explanatory compound separated by hyphens with >= 3
    # parts. ``cross-tenant`` (2 parts) is too short to be a reason on
    # its own; ``view-layer-scoped-via-request-school-or-role-graph``
    # (>= 3 parts) is allowed.
    if len(stripped.split()) < 2 and len(stripped.split("-")) < 3:
        return "one-token"

    return None


def _scan_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return findings

    # Use tokenize so string-literal occurrences (e.g. inside docstrings or
    # in feature registry notes) are not mistaken for real markers.
    try:
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        comments = [
            (tok.start[0], tok.string)
            for tok in tokens
            if tok.type == tokenize.COMMENT
        ]
    except (tokenize.TokenizeError, IndentationError, SyntaxError):
        return findings

    rel = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    for lineno, comment in comments:
        match = _MARKER_RE.search(comment)
        if match is None:
            continue
        reason = match.group("reason") or ""
        kind = _classify(reason)
        if kind is None:
            continue
        findings.append(
            Finding(path=rel, lineno=lineno, reason=reason, kind=kind)
        )
    return findings


def _walk() -> list[Finding]:
    out: list[Finding] = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for py in root.rglob("*.py"):
            if any(p in py.parts for p in ("__pycache__", "node_modules")):
                continue
            out.extend(_scan_file(py))
    out.sort(key=lambda f: (f.path, f.lineno))
    return out


def _read_baseline_count() -> int | None:
    if not BASELINE_PATH.exists():
        return None
    try:
        return int(json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["finding_count"])
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None


def _write_baseline(count: int) -> None:
    from datetime import datetime, timezone

    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "scanner": "scan_tenant_isolation_marker_quality.py",
                "finding_count": count,
                "note": (
                    "Lazy reason strings on # tenant-isolation-allow: markers. "
                    "Increasing this number requires intentional opt-in; the gate "
                    "fails CI when count > baseline."
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Exit 1 when current count exceeds the baseline JSON.",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="Capture current count into the baseline JSON.",
    )
    args = parser.parse_args()

    findings = _walk()
    count = len(findings)

    if args.write_baseline:
        _write_baseline(count)
        print(f"baseline written -> {BASELINE_PATH.relative_to(REPO_ROOT)} ({count})")
        return 0

    if args.json:
        print(
            json.dumps(
                {
                    "finding_count": count,
                    "findings": [asdict(f) for f in findings],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        if not findings:
            print("tenant-isolation marker quality: clean (0 lazy reasons)")
        else:
            print(f"tenant-isolation marker quality: {count} lazy reason(s):")
            for f in findings:
                print(f"  {f.path}:{f.lineno} [{f.kind}] {f.reason!r}")

    if args.compare:
        baseline = _read_baseline_count()
        if baseline is None:
            print(
                "ERROR: baseline file missing; run --write-baseline first",
                file=sys.stderr,
            )
            return 1
        if count > baseline:
            print(
                f"REGRESSION: {count} lazy reasons > baseline {baseline}",
                file=sys.stderr,
            )
            return 1
        if count < baseline:
            print(
                f"NOTE: count {count} below baseline {baseline} -- "
                f"run --write-baseline to lock in the improvement",
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())
