#!/usr/bin/env python3
"""
Doc/plan density discipline verifier.

Purpose: enforce non-growth of overlapping plan/roadmap/remediation/master
markdown files unless intentionally re-baselined with SOT/log updates.

Also verifies the canonical SOT, autonomous log, external backlog, and Cursor rule
files were not replaced by stubs or accidental pastes (title/section markers + minimum
sizes; SOT must still point at per-app depth + backlog — batch 39 §11.4).

Usage: python scripts/verify_doc_plan_density_discipline.py [--base REPO_ROOT]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
ROOT = DEFAULT_ROOT

NAME_PATTERN = re.compile(r"(plan|roadmap|remediation|master)", flags=re.IGNORECASE)

# Baseline from 2026-05-14 (all docs/**/*.md, and root docs/*.md respectively).
MAX_MATCHING_DOCS_TOTAL = 153
MAX_MATCHING_DOCS_ROOT = 119

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

# Match scripts/repair_runmycampus_sot.py — mega-lines are almost always paste/encoding corruption.
_MAX_CANONICAL_LINE_CHARS = 50_000


def _oversized_line_errors(
    path: Path, body: str, root: Path, *, max_chars: int
) -> list[str]:
    errs: list[str] = []
    for i, line in enumerate(body.splitlines(), start=1):
        if len(line) > max_chars:
            errs.append(
                f"{path.relative_to(root)} line {i} exceeds {max_chars} characters "
                f"(len={len(line)}); run scripts/repair_runmycampus_sot.py "
                f"(or --execution-log for the autonomous log)."
            )
    return errs


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _canonical_artifact_paths(root: Path) -> tuple[Path, Path, Path, Path, Path]:
    docs = root / "docs"
    return (
        docs / "RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md",
        docs / "RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md",
        docs / "SOT_REMAINING_ITEMS_BACKLOG.md",
        root / ".cursor" / "rules" / "runmycampus-single-source-of-truth.mdc",
        docs,
    )


def _wave_stanza_reference_errors(root: Path) -> list[str]:
    """1022: Runbook + SOT must list the canonical PATH II shell wave test modules."""
    scripts_dir = str(root / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from wave_shell_test_modules import (
        WAVE_SHELL_TEST_MODULES,
        wave_modules_from_runbook_path,
    )

    errs: list[str] = []
    runbook = root / "docs" / "runbook" / "SOT_VALIDATION_STANZA.md"
    if not runbook.is_file():
        errs.append(
            "Missing docs/runbook/SOT_VALIDATION_STANZA.md "
            "(canonical wave `manage.py test` stanza)."
        )
        return errs
    body = _read_text(runbook)
    try:
        parsed = wave_modules_from_runbook_path(runbook)
    except OSError:
        parsed = ()
    if parsed != WAVE_SHELL_TEST_MODULES:
        errs.append(
            f"{runbook.relative_to(root)} bash stanza module list/order must match "
            f"scripts/wave_shell_test_modules.WAVE_SHELL_TEST_MODULES exactly; "
            f"parsed={list(parsed)!r} canonical={list(WAVE_SHELL_TEST_MODULES)!r}"
        )
    for mod in WAVE_SHELL_TEST_MODULES:
        if mod not in body:
            errs.append(
                f"{runbook.relative_to(root)} missing required module line {mod!r}"
            )
    sot = root / "docs" / "RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md"
    if sot.is_file():
        sot_body = _read_text(sot)
        needle = "docs/runbook/SOT_VALIDATION_STANZA.md"
        if needle not in sot_body:
            errs.append(
                f"{sot.relative_to(root)} must reference {needle!r} "
                "(wave validation stanza runbook)."
            )
    return errs


def _canonical_artifact_errors(root: Path) -> list[str]:
    """Fail fast when SOT, execution log, backlog, or Cursor rule is truncated or stubbed."""
    sot, exec_log, backlog, rule, _docs = _canonical_artifact_paths(root)
    errs: list[str] = []
    if sot.is_file():
        body = _read_text(sot)
        if _SOT_TITLE_SNIPPET not in body:
            errs.append(
                f"{sot.relative_to(root)} missing title marker (possible stub/paste); "
                f"expected substring: {_SOT_TITLE_SNIPPET!r}"
            )
        if _SOT_SECTION_SNIPPET not in body:
            errs.append(
                f"{sot.relative_to(root)} missing section marker (possible stub/paste); "
                f"expected substring: {_SOT_SECTION_SNIPPET!r}"
            )
        if len(body) < _MIN_SOT_CHARS:
            errs.append(
                f"{sot.relative_to(root)} too small ({len(body)} chars < {_MIN_SOT_CHARS}); "
                "restore from git or reload from disk — editor buffer may be a short paste."
            )
        if _SOT_PATH_TO_100_SNIPPET not in body:
            errs.append(
                f"{sot.relative_to(root)} missing per-app depth pointer "
                f"(expected substring {_SOT_PATH_TO_100_SNIPPET!r})"
            )
        if _SOT_BACKLOG_SNIPPET not in body:
            errs.append(
                f"{sot.relative_to(root)} missing external backlog pointer "
                f"(expected substring {_SOT_BACKLOG_SNIPPET!r})"
            )
        errs.extend(
            _oversized_line_errors(sot, body, root, max_chars=_MAX_CANONICAL_LINE_CHARS)
        )
    if exec_log.is_file():
        body = _read_text(exec_log)
        if _LOG_TITLE_SNIPPET not in body:
            errs.append(
                f"{exec_log.relative_to(root)} missing title marker; "
                f"expected substring: {_LOG_TITLE_SNIPPET!r}"
            )
        if len(body) < _MIN_EXEC_LOG_CHARS:
            errs.append(
                f"{exec_log.relative_to(root)} too small ({len(body)} chars < {_MIN_EXEC_LOG_CHARS})"
            )
        errs.extend(
            _oversized_line_errors(
                exec_log, body, root, max_chars=_MAX_CANONICAL_LINE_CHARS
            )
        )
    if backlog.is_file():
        body = _read_text(backlog)
        if _BACKLOG_TITLE_SNIPPET not in body:
            errs.append(
                f"{backlog.relative_to(root)} missing title marker; "
                f"expected substring: {_BACKLOG_TITLE_SNIPPET!r}"
            )
        if _BACKLOG_AUTHORITY_SNIPPET not in body:
            errs.append(
                f"{backlog.relative_to(root)} missing SOT authority link "
                f"(expected substring {_BACKLOG_AUTHORITY_SNIPPET!r})"
            )
        if _BACKLOG_OPEN_SECTION_SNIPPET not in body:
            errs.append(
                f"{backlog.relative_to(root)} missing external OPEN section "
                f"(expected heading {_BACKLOG_OPEN_SECTION_SNIPPET!r})"
            )
        if len(body) < _MIN_BACKLOG_CHARS:
            errs.append(
                f"{backlog.relative_to(root)} too small ({len(body)} chars < {_MIN_BACKLOG_CHARS})"
            )
    if rule.is_file():
        body = _read_text(rule)
        if _RULE_PATH_SNIPPET not in body:
            errs.append(
                f"{rule.relative_to(root)} missing SOT path reference; "
                f"expected substring: {_RULE_PATH_SNIPPET!r}"
            )
        if len(body) < _MIN_RULE_CHARS:
            errs.append(
                f"{rule.relative_to(root)} too small ({len(body)} chars < {_MIN_RULE_CHARS})"
            )
    return errs


def _matching_doc_paths(root: Path) -> tuple[list[Path], list[Path]]:
    docs = root / "docs"
    all_docs = [p for p in docs.rglob("*.md") if NAME_PATTERN.search(p.name)]
    root_docs = [p for p in docs.glob("*.md") if NAME_PATTERN.search(p.name)]
    return all_docs, root_docs


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify SOT/log density discipline and canonical doc markers."
    )
    parser.add_argument(
        "--base",
        default=str(DEFAULT_ROOT),
        help="Repository root (default: directory containing this script's parent).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"verify_doc_plan_density_discipline: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []
    sot, exec_log, backlog, rule, _docs = _canonical_artifact_paths(root)

    for path in (sot, exec_log, backlog, rule):
        if not path.is_file():
            errors.append(f"Missing required discipline artifact: {path.relative_to(root)}")

    errors.extend(_canonical_artifact_errors(root))
    errors.extend(_wave_stanza_reference_errors(root))

    all_docs, root_docs = _matching_doc_paths(root)
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
    raise SystemExit(main(None))
