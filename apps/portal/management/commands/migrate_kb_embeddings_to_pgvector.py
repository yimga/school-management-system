"""
Backfill portal_kbarticle.vector_embedding JSON → embedding_vec (pgvector).

Mirrors analytics migrate_embeddings_to_pgvector for KB articles (batch 1354).
"""

from __future__ import annotations

import logging
import math

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

logger = logging.getLogger("apps.portal.commands.migrate_kb_embeddings_to_pgvector")

_TABLE = "portal_kbarticle"
_INDEX_NAME = "portal_kbarticle_embedding_vec_ivfflat"
_DEFAULT_BATCH = 500


class Command(BaseCommand):
    help = "Add embedding_vec to portal_kbarticle and backfill from vector_embedding JSON."

    def add_arguments(self, parser):
        parser.add_argument("--dimensions", type=int, default=None)
        parser.add_argument("--batch-size", type=int, default=_DEFAULT_BATCH)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        if connection.vendor != "postgresql":
            raise CommandError(
                f"pgvector requires PostgreSQL; current vendor is {connection.vendor}."
            )
        dim = opts.get("dimensions") or self._detect_dim()
        if not dim:
            raise CommandError(
                "Could not detect embedding dimension — pass --dimensions N."
            )
        dry = bool(opts.get("dry_run"))
        batch = int(opts.get("batch_size") or _DEFAULT_BATCH)
        if dry:
            self.stdout.write(f"[dry] would enable vector extension and add dim={dim}")
            return
        with connection.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            cur.execute(
                f"ALTER TABLE {_TABLE} "
                f"ADD COLUMN IF NOT EXISTS embedding_vec vector({dim});"
            )
            row_count = self._count_rows(cur)
            lists = max(50, min(5000, int(math.ceil(math.sqrt(max(row_count, 1))))))
            while True:
                cur.execute(
                    f"""
                    UPDATE {_TABLE} t
                    SET embedding_vec = (t.vector_embedding::text)::vector
                    FROM (
                        SELECT id FROM {_TABLE}
                        WHERE embedding_vec IS NULL
                          AND vector_embedding IS NOT NULL
                          AND vector_embedding::text <> '[]'
                        LIMIT %s
                    ) sub
                    WHERE t.id = sub.id
                    """,
                    [batch],
                )
                if cur.rowcount == 0:
                    break
                self.stdout.write(f"backfilled batch: {cur.rowcount}")
            cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS {_INDEX_NAME}
                ON {_TABLE}
                USING ivfflat (embedding_vec vector_cosine_ops)
                WITH (lists = {lists});
                """
            )
        self.stdout.write(self.style.SUCCESS(f"KB pgvector migration complete (dim={dim})"))

    def _count_rows(self, cur) -> int:
        cur.execute(
            f"SELECT COUNT(*) FROM {_TABLE} WHERE vector_embedding IS NOT NULL"
        )
        return int(cur.fetchone()[0])

    def _detect_dim(self) -> int | None:
        with connection.cursor() as cur:
            cur.execute(
                f"""
                SELECT vector_embedding FROM {_TABLE}
                WHERE vector_embedding IS NOT NULL
                  AND vector_embedding::text <> '[]'
                LIMIT 1
                """
            )
            row = cur.fetchone()
        if not row or not row[0]:
            return None
        vec = row[0]
        if isinstance(vec, list) and vec:
            return len(vec)
        return None
