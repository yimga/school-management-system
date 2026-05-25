#!/usr/bin/env python3
"""Verify high-stakes workflow KB articles have editorial content (not stubs)."""

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
from apps.portal.workflow_kb_corpus import slug_for_workflow_id
from apps.portal.workflow_kb_corpus_editorial import HIGH_STAKES_WORKFLOW_IDS

_MIN_CONTENT_LEN = 400
_REQUIRED_MARKERS = ("<h2>", "<h3>", "<ol>", "Pre-flight")


def main() -> int:
    failures: list[str] = []
    for wid in sorted(HIGH_STAKES_WORKFLOW_IDS):
        slug = slug_for_workflow_id(wid)
        article = KBArticle.objects.filter(
            slug=slug, school__isnull=True, status="PUBLISHED"
        ).first()
        if article is None:
            failures.append(f"missing published article: {wid} ({slug})")
            continue
        content = (article.content or "") + (article.content_html or "")
        if len(content) < _MIN_CONTENT_LEN:
            failures.append(f"content too short: {wid} ({len(content)} chars)")
        if not all(marker in content for marker in _REQUIRED_MARKERS[:3]):
            failures.append(f"missing structure markers: {wid}")
        preflight_ok = any(
            token in content.lower()
            for token in ("pre-flight", "pre-flight checklist", "before you start", "checklist")
        )
        if not preflight_ok:
            failures.append(f"missing pre-flight/checklist section: {wid}")

    if failures:
        print("verify_workflow_kb_editorial: FAIL", file=sys.stderr)
        for line in failures[:12]:
            print(f"  - {line}", file=sys.stderr)
        print("  hint: python manage.py seed_workflow_kb_corpus", file=sys.stderr)
        return 1

    print(
        "verify_workflow_kb_editorial: WORKFLOW_KB_EDITORIAL_PASS "
        f"({len(HIGH_STAKES_WORKFLOW_IDS)} high-stakes runbooks)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
