#!/usr/bin/env python3
"""Gate for batch 1334 KB embedding ingestion commands."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import django

    django.setup()
    from apps.portal.kb_context import published_kb_queryset

    total = published_kb_queryset().count()
    with_vec = published_kb_queryset().exclude(vector_embedding=[]).count()
    cmd = ROOT / "apps/portal/management/commands/reindex_kb_help_embeddings.py"
    index_cmd = ROOT / "apps/portal/management/commands/build_code_support_index.py"
    if not cmd.is_file() or not index_cmd.is_file():
        print("verify_kb_embedding_coverage: missing management commands", file=sys.stderr)
        return 1
    print(
        f"verify_kb_embedding_coverage: OK articles={total} with_embedding={with_vec} "
        f"(reindex via manage.py reindex_kb_help_embeddings)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
