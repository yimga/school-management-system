"""Periodically rebuild the IVFFLAT index with a tuned `lists` parameter.

IVFFLAT performance degrades as a table grows past the `lists` value
the index was built with. Convention: lists ≈ sqrt(rows). When the row
count has grown 4× or more since the last index build, recall starts
to suffer because each list bucket holds too many vectors.

Recommended cadence: monthly during low-traffic window.

Steps (executed inside one transaction so a failure rolls back cleanly):
  1. Compute new lists = ceil(sqrt(current_row_count)).
  2. `DROP INDEX IF EXISTS aiembedding_vec_ivfflat;`
  3. `CREATE INDEX … USING ivfflat … WITH (lists = N);`
  4. `VACUUM ANALYZE siteconfig_aiembeddingstore;` (autocommit; outside txn)

Refuses to drop the index when no embedding_vec column exists.
"""

from __future__ import annotations

import logging
import math

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

logger = logging.getLogger("apps.analytics.commands.rebuild_pgvector_index")

_TABLE = "siteconfig_aiembeddingstore"
_INDEX_NAME = "aiembedding_vec_ivfflat"
_MIN_LISTS = 50
_MAX_LISTS = 5000


class Command(BaseCommand):
    help = "Drop and rebuild the IVFFLAT index with a freshly-tuned `lists` parameter."

    def add_arguments(self, parser):
        parser.add_argument(
            "--lists", type=int, default=None,
            help="Override the auto-tuned lists parameter.",
        )
        parser.add_argument(
            "--vacuum", action="store_true",
            help="Run `VACUUM ANALYZE` after rebuild (recommended; "
            "must be outside transaction so it can't be wrapped here).",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        if connection.vendor != "postgresql":
            raise CommandError(
                f"pgvector requires PostgreSQL; current vendor is "
                f"{connection.vendor}."
            )

        # Confirm the column exists before we drop the index it depends on.
        with connection.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM pg_attribute "
                "WHERE attrelid = %s::regclass AND attname = 'embedding_vec' "
                "AND NOT attisdropped LIMIT 1",
                [_TABLE],
            )
            if not cur.fetchone():
                raise CommandError(
                    "embedding_vec column doesn't exist. "
                    "Run `migrate_embeddings_to_pgvector` first."
                )

            cur.execute(
                f"SELECT COUNT(*) FROM {_TABLE} "
                f"WHERE lifecycle_status = 'active' AND embedding_vec IS NOT NULL"
            )
            row_count = cur.fetchone()[0]

        lists = opts.get("lists") or self._auto_lists(row_count)
        self.stdout.write(
            f"  rows_with_vector={row_count}  lists={lists}"
        )

        drop_sql = f"DROP INDEX IF EXISTS {_INDEX_NAME};"
        create_sql = (
            f"CREATE INDEX {_INDEX_NAME} "
            f"ON {_TABLE} USING ivfflat "
            f"(embedding_vec vector_cosine_ops) "
            f"WITH (lists = {lists});"
        )

        if opts.get("dry_run"):
            self.stdout.write(f"  [dry] {drop_sql}")
            self.stdout.write(f"  [dry] {create_sql}")
            if opts.get("vacuum"):
                self.stdout.write(f"  [dry] VACUUM ANALYZE {_TABLE};")
            return

        with transaction.atomic():
            with connection.cursor() as cur:
                self.stdout.write(f"  {drop_sql}")
                cur.execute(drop_sql)
                self.stdout.write(f"  {create_sql}")
                cur.execute(create_sql)
        self.stdout.write(self.style.SUCCESS(
            f"Rebuilt {_INDEX_NAME} (lists={lists})."
        ))

        if opts.get("vacuum"):
            # VACUUM can't run inside a transaction.
            old_autocommit = connection.get_autocommit()
            connection.set_autocommit(True)
            try:
                with connection.cursor() as cur:
                    sql = f"VACUUM ANALYZE {_TABLE};"
                    self.stdout.write(f"  {sql}")
                    cur.execute(sql)
                self.stdout.write(self.style.SUCCESS("VACUUM ANALYZE complete."))
            finally:
                connection.set_autocommit(old_autocommit)

    def _auto_lists(self, row_count: int) -> int:
        if row_count <= 0:
            return _MIN_LISTS
        tuned = int(math.ceil(math.sqrt(row_count)))
        return max(_MIN_LISTS, min(_MAX_LISTS, tuned))
