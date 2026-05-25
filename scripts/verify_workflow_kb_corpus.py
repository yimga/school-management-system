#!/usr/bin/env python3
"""Verify Phase 9 workflow KB corpus covers audit gaps (teacher/parent + missing workflows)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from apps.portal.models_kb import KBArticle
from apps.portal.workflow_kb_corpus import (
    ALL_WORKFLOW_KB_CORPUS,
    PARENT_WORKFLOW_SLUGS,
    TEACHER_WORKFLOW_SLUGS,
    slug_for_workflow_id,
)
from apps.portal.workflow_kb_corpus_audit import load_phase9_audit_rows


def main() -> int:
    missing_slugs: list[str] = []
    unpublished: list[str] = []
    for row in ALL_WORKFLOW_KB_CORPUS:
        slug = row["slug"]
        qs = KBArticle.objects.filter(slug=slug, school__isnull=True)
        if not qs.exists():
            missing_slugs.append(slug)
        elif not qs.filter(status="PUBLISHED").exists():
            unpublished.append(slug)

    teacher_present = sum(
        1
        for slug in TEACHER_WORKFLOW_SLUGS
        if KBArticle.objects.filter(
            slug=slug, school__isnull=True, status="PUBLISHED"
        ).exists()
    )
    parent_present = sum(
        1
        for slug in PARENT_WORKFLOW_SLUGS
        if KBArticle.objects.filter(
            slug=slug, school__isnull=True, status="PUBLISHED"
        ).exists()
    )

    audit_missing_rows = [
        w
        for w in load_phase9_audit_rows()
        if not (
            (w.get("help_article_status") == "exists")
            and (w.get("help_article_path") or "").startswith("templates/")
        )
    ]
    audit_uncovered: list[str] = []
    for row in audit_missing_rows:
        wid = row.get("workflow_id") or ""
        slug = slug_for_workflow_id(wid)
        if not KBArticle.objects.filter(
            slug=slug, school__isnull=True, status="PUBLISHED"
        ).exists():
            audit_uncovered.append(wid)

    if (
        missing_slugs
        or unpublished
        or teacher_present == 0
        or parent_present == 0
        or audit_uncovered
    ):
        print("verify_workflow_kb_corpus: FAIL", file=sys.stderr)
        if missing_slugs:
            print(f"  missing slugs ({len(missing_slugs)})", file=sys.stderr)
        if unpublished:
            print(f"  unpublished ({len(unpublished)})", file=sys.stderr)
        if teacher_present == 0:
            print("  teacher workflow coverage: 0%", file=sys.stderr)
        if parent_present == 0:
            print("  parent workflow coverage: 0%", file=sys.stderr)
        if audit_uncovered:
            print(
                f"  audit gaps without KB ({len(audit_uncovered)}): "
                f"{', '.join(audit_uncovered[:6])}",
                file=sys.stderr,
            )
        print("  hint: python manage.py seed_workflow_kb_corpus", file=sys.stderr)
        return 1

    covered = len(audit_missing_rows)
    print(
        "verify_workflow_kb_corpus: WORKFLOW_KB_CORPUS_PASS "
        f"({len(ALL_WORKFLOW_KB_CORPUS)} articles; "
        f"teacher {teacher_present}/{len(TEACHER_WORKFLOW_SLUGS)}; "
        f"parent {parent_present}/{len(PARENT_WORKFLOW_SLUGS)}; "
        f"audit-missing covered {covered}/{covered})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
