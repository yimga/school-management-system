#!/usr/bin/env python3
"""All workflow KB articles must meet enriched editorial structure (batch 1500)."""

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
from apps.portal.workflow_kb_corpus import ALL_WORKFLOW_KB_CORPUS, slug_for_workflow_id

_MIN_LEN = 350
_MARKERS = ("<h2>", "<h3>", "<ol>", "Pre-flight")


def main() -> int:
    failures: list[str] = []
    for row in ALL_WORKFLOW_KB_CORPUS:
        wid = row["workflow_id"]
        slug = slug_for_workflow_id(wid)
        article = KBArticle.objects.filter(
            slug=slug, school__isnull=True, status="PUBLISHED"
        ).first()
        if article is None:
            failures.append(f"missing: {wid}")
            continue
        content = (article.content or "") + (article.content_html or "")
        if len(content) < _MIN_LEN:
            failures.append(f"short: {wid} ({len(content)})")
        if not all(m in content for m in _MARKERS[:3]):
            failures.append(f"structure: {wid}")
        if "pre-flight" not in content.lower() and "checklist" not in content.lower():
            failures.append(f"preflight: {wid}")

    if failures:
        print("verify_workflow_kb_corpus_quality: FAIL", file=sys.stderr)
        for line in failures[:15]:
            print(f"  - {line}", file=sys.stderr)
        print("  hint: python manage.py seed_workflow_kb_corpus", file=sys.stderr)
        return 1
    print(
        "verify_workflow_kb_corpus_quality: WORKFLOW_KB_CORPUS_QUALITY_PASS "
        f"({len(ALL_WORKFLOW_KB_CORPUS)} articles)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
