#!/usr/bin/env python3
"""Refresh Phase 9 audit workflow rows when published KB articles exist."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

AUDIT_PATH = ROOT / "docs" / "generated" / "workflow_help_kb_faq_audit.json"


def main() -> int:
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from apps.portal.models_kb import KBArticle
    from apps.portal.workflow_kb_corpus import slug_for_workflow_id

    if not AUDIT_PATH.is_file():
        print("refresh_workflow_help_kb_audit: audit JSON missing", file=sys.stderr)
        return 1

    data = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    workflows = data.get("workflows") or []
    updated = 0
    for row in workflows:
        path = (row.get("help_article_path") or "").strip()
        if row.get("help_article_status") == "exists" and path.startswith("templates/"):
            continue
        wid = row.get("workflow_id") or ""
        slug = slug_for_workflow_id(wid)
        if not slug:
            continue
        if KBArticle.objects.filter(
            slug=slug, school__isnull=True, status="PUBLISHED"
        ).exists():
            row["help_article_status"] = "exists"
            row["help_article_path"] = f"kb:workflow/{slug}"
            updated += 1

    data["workflows"] = workflows
    data["kb_corpus_refresh_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    missing = sum(
        1
        for w in workflows
        if not (
            (w.get("help_article_status") == "exists")
            and (
                (w.get("help_article_path") or "").startswith("templates/")
                or (w.get("help_article_path") or "").startswith("kb:")
            )
        )
    )
    data["summary"] = {
        **(data.get("summary") or {}),
        "workflows_total": len(workflows),
        "workflows_missing_help": missing,
        "workflows_with_kb_article": len(workflows) - missing,
    }
    AUDIT_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(
        f"refresh_workflow_help_kb_audit: updated {updated} rows; "
        f"missing={missing}/{len(workflows)}"
    )
    return 0 if missing == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
