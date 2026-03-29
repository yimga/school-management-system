#!/usr/bin/env python3
"""
Doc/plan density discipline verifier.

Purpose: enforce non-growth of overlapping plan/roadmap/remediation/master
markdown files unless intentionally re-baselined with SOT/log updates.

Also verifies the canonical SOT, autonomous log, external backlog, and Cursor rule
files were not replaced by stubs or accidental pastes (title/section markers + minimum
sizes; SOT must still point at per-app depth + backlog — batch 39 §11.4).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
SOT = DOCS / "RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md"
EXEC_LOG = DOCS / "RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md"
BACKLOG = DOCS / "SOT_REMAINING_ITEMS_BACKLOG.md"
RULE = ROOT / ".cursor" / "rules" / "runmycampus-single-source-of-truth.mdc"

NAME_PATTERN = re.compile(r"(plan|roadmap|remediation|master)", flags=re.IGNORECASE)

# Baseline from 2026-03-26 (all docs/**/*.md, and root docs/*.md respectively).
MAX_MATCHING_DOCS_TOTAL = 144
MAX_MATCHING_DOCS_ROOT = 114

# Detect accidental editor overwrites (paste / stub) — stable substrings from canonical files.
_SOT_TITLE_SNIPPET = "# RunMyCampus — single execution source of truth"
_SOT_SECTION_SNIPPET = "## At a glance"
_SOT_PATH_TO_100_SNIPPET = "PATH_TO_100_PERCENT_EXECUTION_PLAN.md"
_SOT_BACKLOG_SNIPPET = "SOT_REMAINING_ITEMS_BACKLOG.md"
_LOG_TITLE_SNIPPET = "# RunMyCampus autonomous execution log"
_BACKLOG_TITLE_SNIPPET = "# SOT backlog"
_BACKLOG_AUTHORITY_SNIPPET = "RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md"
_BACKLOG_OPEN_SECTION_SNIPPET = "## External / organizational"
_RULE_PATH_SNIPPET = "docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md"
_MIN_SOT_CHARS = 4000
_MIN_EXEC_LOG_CHARS = 10_000
_MIN_BACKLOG_CHARS = 2000
_MIN_RULE_CHARS = 400


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _canonical_artifact_errors() -> list[str]:
    """Fail fast when SOT, execution log, backlog, or Cursor rule is truncated or stubbed."""
    errs: list[str] = []
    if SOT.is_file():
        body = _read_text(SOT)
        if _SOT_TITLE_SNIPPET not in body:
            errs.append(
                f"{SOT.relative_to(ROOT)} missing title marker (possible stub/paste); "
                f"expected substring: {_SOT_TITLE_SNIPPET!r}"
            )
        if _SOT_SECTION_SNIPPET not in body:
            errs.append(
                f"{SOT.relative_to(ROOT)} missing section marker (possible stub/paste); "
                f"expected substring: {_SOT_SECTION_SNIPPET!r}"
            )
        if len(body) < _MIN_SOT_CHARS:
            errs.append(
                f"{SOT.relative_to(ROOT)} too small ({len(body)} chars < {_MIN_SOT_CHARS}); "
                "restore from git or reload from disk — editor buffer may be a short paste."
            )
        if _SOT_PATH_TO_100_SNIPPET not in body:
            errs.append(
                f"{SOT.relative_to(ROOT)} missing per-app depth pointer "
                f"(expected substring {_SOT_PATH_TO_100_SNIPPET!r})"
            )
        if _SOT_BACKLOG_SNIPPET not in body:
            errs.append(
                f"{SOT.relative_to(ROOT)} missing external backlog pointer "
                f"(expected substring {_SOT_BACKLOG_SNIPPET!r})"
            )
    if EXEC_LOG.is_file():
        body = _read_text(EXEC_LOG)
        if _LOG_TITLE_SNIPPET not in body:
            errs.append(
                f"{EXEC_LOG.relative_to(ROOT)} missing title marker; "
                f"expected substring: {_LOG_TITLE_SNIPPET!r}"
            )
        if len(body) < _MIN_EXEC_LOG_CHARS:
            errs.append(
                f"{EXEC_LOG.relative_to(ROOT)} too small ({len(body)} chars < {_MIN_EXEC_LOG_CHARS})"
            )
    if BACKLOG.is_file():
        body = _read_text(BACKLOG)
        if _BACKLOG_TITLE_SNIPPET not in body:
            errs.append(
                f"{BACKLOG.relative_to(ROOT)} missing title marker; "
                f"expected substring: {_BACKLOG_TITLE_SNIPPET!r}"
            )
        if _BACKLOG_AUTHORITY_SNIPPET not in body:
            errs.append(
                f"{BACKLOG.relative_to(ROOT)} missing SOT authority link "
                f"(expected substring {_BACKLOG_AUTHORITY_SNIPPET!r})"
            )
        if _BACKLOG_OPEN_SECTION_SNIPPET not in body:
            errs.append(
                f"{BACKLOG.relative_to(ROOT)} missing external OPEN section "
                f"(expected heading {_BACKLOG_OPEN_SECTION_SNIPPET!r})"
            )
        if len(body) < _MIN_BACKLOG_CHARS:
            errs.append(
                f"{BACKLOG.relative_to(ROOT)} too small ({len(body)} chars < {_MIN_BACKLOG_CHARS})"
            )
    if RULE.is_file():
        body = _read_text(RULE)
        if _RULE_PATH_SNIPPET not in body:
            errs.append(
                f"{RULE.relative_to(ROOT)} missing SOT path reference; "
                f"expected substring: {_RULE_PATH_SNIPPET!r}"
            )
        if len(body) < _MIN_RULE_CHARS:
            errs.append(
                f"{RULE.relative_to(ROOT)} too small ({len(body)} chars < {_MIN_RULE_CHARS})"
            )
    return errs


def _matching_doc_paths() -> tuple[list[Path], list[Path]]:
    all_docs = [p for p in DOCS.rglob("*.md") if NAME_PATTERN.search(p.name)]
    root_docs = [p for p in DOCS.glob("*.md") if NAME_PATTERN.search(p.name)]
    return all_docs, root_docs


def main() -> int:
    errors: list[str] = []

    for path in (SOT, EXEC_LOG, BACKLOG, RULE):
        if not path.is_file():
            errors.append(f"Missing required discipline artifact: {path.relative_to(ROOT)}")

    errors.extend(_canonical_artifact_errors())

    all_docs, root_docs = _matching_doc_paths()
    all_count = len(all_docs)
    root_count = len(root_docs)

    if all_count > MAX_MATCHING_DOCS_TOTAL:
        errors.append(
            "docs plan-density exceeded: "
            f"{all_count} > {MAX_MATCHING_DOCS_TOTAL} matching docs/**/*.md files."
        )
    if root_count > MAX_MATCHING_DOCS_ROOT:
        errors.append(
            "docs root plan-density exceeded: "
            f"{root_count} > {MAX_MATCHING_DOCS_ROOT} matching docs/*.md files."
        )

    if errors:
        print("verify_doc_plan_density_discipline: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print(
        "verify_doc_plan_density_discipline: PASS "
        f"(SOT/log/rule markers + size OK; matching_docs_total={all_count}, "
        f"matching_docs_root={root_count})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
