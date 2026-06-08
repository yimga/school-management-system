"""One-shot migration: AIEmbeddingStore.embedding (JSON) → embedding_vec (vector).

Pgvector isn't enabled in the default migration chain because the
Postgres extension is operator-installed. This command runs after the
operator has enabled the extension and bumps the schema atomically.

Production-scale features (5k+ rows per tenant):
  * Auto-tunes IVFFLAT `lists` = ceil(sqrt(row_count)) when not given
    — recommended convention in pgvector docs.
  * Backfills the JSON→vector copy in batches (default 1000 rows) with
    progress reporting, so a large table doesn't hold a row-level lock
    for minutes.
  * Refuses to run when an existing `embedding_vec` column has a
    different dimension than the current data — auto-recover is too
    dangerous (silent truncation or NULL coercion). Operator must
    explicitly `--force-drop-column` for the destructive path.

Steps (each idempotent — re-running is safe):
  1. `CREATE EXTENSION IF NOT EXISTS vector;`
  2. `ALTER TABLE … ADD COLUMN IF NOT EXISTS embedding_vec vector(N);`
  3. Batched `UPDATE … SET embedding_vec = (embedding::text)::vector`
     for rows where embedding_vec IS NULL.
  4. `CREATE INDEX IF NOT EXISTS aiembedding_vec_ivfflat …` with tuned
     `lists` parameter.

After this runs, set `PGVECTOR_ENABLED=True` in settings/env and
`search_students` switches to the vector code path on its next call.
Pass `--write-env-flag` to have the command do that itself.

Refuses to run if the DB is not PostgreSQL — pgvector requires Postgres.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

logger = logging.getLogger("apps.analytics.commands.migrate_embeddings_to_pgvector")

_DEFAULT_BATCH_SIZE = 1000
_ENV_FLAG = "PGVECTOR_ENABLED=True"
# Floor for IVFFLAT lists — fewer lists is slower but uses less memory.
_MIN_INDEX_LISTS = 50
# Cap to prevent absurd values from a row-count auto-tune on huge tables;
# beyond this, IVFFLAT itself stops scaling well — use HNSW instead
# (separate operator decision tracked outside this command).
_MAX_INDEX_LISTS = 5000


class Command(BaseCommand):
    help = "Backfill AIEmbeddingStore.embedding into a pgvector column."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dimensions", type=int, default=None,
            help="Vector dimension. Auto-detected from first row when omitted.",
        )
        parser.add_argument(
            "--index-lists", type=int, default=None,
            help="Lists for the IVFFLAT index. Auto-tuned to ceil(sqrt(row_count)) "
            f"(clamped to [{_MIN_INDEX_LISTS}, {_MAX_INDEX_LISTS}]) when omitted.",
        )
        parser.add_argument(
            "--batch-size", type=int, default=_DEFAULT_BATCH_SIZE,
            help="Rows per UPDATE batch during backfill (default 1000). Reduce "
            "if the DB is under heavy concurrent write load.",
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--write-env-flag", action="store_true",
            help="Append PGVECTOR_ENABLED=True to .env after a successful "
            "apply so the search path activates without manual edit.",
        )
        parser.add_argument(
            "--force-drop-column", action="store_true",
            help="DROP and recreate the embedding_vec column when its dimension "
            "differs from the current embedding data. Irreversible loss of "
            "previously-backfilled vectors. Required when migrating to a new "
            "embedding model with different dim.",
        )

    def handle(self, *args, **opts):
        vendor = connection.vendor
        if vendor != "postgresql":
            raise CommandError(
                f"pgvector requires PostgreSQL; current vendor is {vendor}."
            )

        row_count = self._count_indexable_rows()
        dim = opts.get("dimensions") or self._detect_dimensions()
        if not dim and row_count == 0:
            # Fresh deploys have no AIEmbeddingStore rows yet — pgvector setup
            # is deferred until build_student_embeddings / index_ai_knowledge runs.
            self.stdout.write(self.style.SUCCESS(
                "Skipping pgvector migration: no embedding rows and --dimensions "
                "not set. Re-run after embeddings are indexed, or pass "
                "--dimensions explicitly."
            ))
            return

        if not dim:
            raise CommandError(
                "Could not auto-detect dimensions and --dimensions wasn't passed. "
                "Either index at least one row first or specify --dimensions."
            )

        # Row count — used for both progress reporting and IVFFLAT auto-tune.
        lists = opts.get("index_lists") or self._auto_lists(row_count)
        self.stdout.write(
            f"  vector dim={dim}  rows_to_index~={row_count}  ivfflat_lists={lists}"
        )

        # Detect existing-column dimension conflict BEFORE the destructive UPDATE.
        existing_dim = self._existing_column_dim()
        if existing_dim is not None and existing_dim != dim:
            if not opts.get("force_drop_column"):
                raise CommandError(
                    f"embedding_vec column already exists with dim={existing_dim} "
                    f"but current data is dim={dim}. "
                    "Pass --force-drop-column to drop and recreate (loss of "
                    "previously-backfilled vectors)."
                )
            self.stdout.write(self.style.WARNING(
                f"Dropping existing embedding_vec column (dim={existing_dim}) "
                f"and dependent index per --force-drop-column."
            ))
            if not opts.get("dry_run"):
                self._exec("DROP INDEX IF EXISTS aiembedding_vec_ivfflat;")
                self._exec(
                    "ALTER TABLE siteconfig_aiembeddingstore "
                    "DROP COLUMN IF EXISTS embedding_vec;"
                )

        # Step 1+2: extension + column (idempotent).
        self._exec_each([
            "CREATE EXTENSION IF NOT EXISTS vector;",
            (
                f"ALTER TABLE siteconfig_aiembeddingstore "
                f"ADD COLUMN IF NOT EXISTS embedding_vec vector({dim});"
            ),
        ], dry_run=opts.get("dry_run"))

        # Step 3: batched backfill.
        if not opts.get("dry_run"):
            self._batched_backfill(opts["batch_size"])
        else:
            self.stdout.write(
                f"  [dry] would batched-backfill embedding_vec in chunks of "
                f"{opts['batch_size']}"
            )

        # Step 4: index.
        self._exec_each([
            f"CREATE INDEX IF NOT EXISTS aiembedding_vec_ivfflat "
            f"ON siteconfig_aiembeddingstore USING ivfflat "
            f"(embedding_vec vector_cosine_ops) "
            f"WITH (lists = {lists});",
        ], dry_run=opts.get("dry_run"))

        if opts.get("dry_run"):
            self.stdout.write(self.style.SUCCESS(
                f"Dry-run complete (vector dim={dim}, lists={lists}). "
                f"No DB changes applied."
            ))
            return
        self.stdout.write(self.style.SUCCESS(
            f"pgvector migration applied (dim={dim}, rows~={row_count}, "
            f"lists={lists})."
        ))
        if opts.get("write_env_flag"):
            self._append_env_flag()
        else:
            self.stdout.write(
                f"Next: set {_ENV_FLAG} in your environment (or re-run "
                "this command with --write-env-flag to append it to .env)."
            )

    def _auto_lists(self, row_count: int) -> int:
        """Convention: lists ≈ sqrt(rows). Clamped to a sane range."""
        if row_count <= 0:
            return _MIN_INDEX_LISTS
        tuned = int(math.ceil(math.sqrt(row_count)))
        return max(_MIN_INDEX_LISTS, min(_MAX_INDEX_LISTS, tuned))

    def _count_indexable_rows(self) -> int:
        """Count rows with a non-empty embedding."""
        from apps.siteconfig.models import AIEmbeddingStore
        # tenant-isolation-allow: public-schema embedding store; row count for sizing.
        try:
            return AIEmbeddingStore.objects.filter(
                lifecycle_status="active"
            ).exclude(embedding=[]).count()
        except Exception:  # noqa: BLE001 — sizing is non-critical
            return 0

    def _existing_column_dim(self) -> int | None:
        """Return the dim of embedding_vec if the column already exists, else None.

        Reads from information_schema. Postgres-specific; this method
        is only called on the postgresql vendor branch.
        """
        sql = """
            SELECT atttypmod
            FROM pg_attribute
            WHERE attrelid = 'siteconfig_aiembeddingstore'::regclass
              AND attname = 'embedding_vec'
              AND NOT attisdropped
            LIMIT 1
        """
        try:
            with connection.cursor() as cur:
                cur.execute(sql)
                row = cur.fetchone()
        except Exception:  # noqa: BLE001 — column or table absent
            return None
        if not row or row[0] is None:
            return None
        # pgvector stores dim in atttypmod directly (no VARHDRSZ subtraction).
        return int(row[0])

    def _batched_backfill(self, batch_size: int) -> None:
        """UPDATE pending rows in batches with a COMMIT per batch.

        Pg keeps a row-level lock per UPDATE until the surrounding
        transaction commits — batching means we don't hold thousands of
        locks at once during a multi-minute backfill.
        """
        total_done = 0
        while True:
            with transaction.atomic():
                with connection.cursor() as cur:
                    # CTE so we limit the batch by PK lookup, not WHERE+LIMIT
                    # (which Pg can't combine on UPDATE without a sub-select).
                    cur.execute(f"""
                        WITH batch AS (
                            SELECT id FROM siteconfig_aiembeddingstore
                            WHERE embedding_vec IS NULL
                              AND lifecycle_status = 'active'
                              AND embedding IS NOT NULL
                              AND jsonb_typeof(embedding::jsonb) = 'array'
                            ORDER BY id
                            LIMIT {int(batch_size)}
                        )
                        UPDATE siteconfig_aiembeddingstore AS t
                        SET embedding_vec = (t.embedding::text)::vector
                        FROM batch
                        WHERE t.id = batch.id
                    """)
                    updated = cur.rowcount or 0
            total_done += updated
            self.stdout.write(f"  backfill: +{updated} rows  (total={total_done})")
            if updated < batch_size:
                break

    def _exec(self, sql: str) -> None:
        with connection.cursor() as cur:
            cur.execute(sql)

    def _exec_each(self, statements: list[str], *, dry_run: bool) -> None:
        for sql in statements:
            self.stdout.write(f"  {sql}")
            if dry_run:
                continue
            self._exec(sql)

    def _append_env_flag(self):
        """Idempotently append PGVECTOR_ENABLED=True to .env at BASE_DIR.

        Reads any existing .env first to avoid duplicate lines or
        conflicting `PGVECTOR_ENABLED=False` entries.
        """
        env_path = Path(getattr(settings, "BASE_DIR", Path("."))) / ".env"
        existing = ""
        if env_path.exists():
            existing = env_path.read_text(encoding="utf-8")
            if "PGVECTOR_ENABLED=True" in existing:
                self.stdout.write(
                    f".env already has PGVECTOR_ENABLED=True — no change."
                )
                return
            if "PGVECTOR_ENABLED=" in existing:
                # Replace any existing line (False / 0 / blank) in place.
                lines = []
                replaced = False
                for line in existing.splitlines():
                    if line.strip().startswith("PGVECTOR_ENABLED="):
                        lines.append(_ENV_FLAG)
                        replaced = True
                    else:
                        lines.append(line)
                if replaced:
                    env_path.write_text(
                        "\n".join(lines) + "\n", encoding="utf-8",
                    )
                    self.stdout.write(
                        f"Updated existing PGVECTOR_ENABLED line in {env_path}."
                    )
                    return
        # Append at the end.
        with open(env_path, "a", encoding="utf-8") as f:
            if existing and not existing.endswith("\n"):
                f.write("\n")
            f.write("\n# Auto-set by migrate_embeddings_to_pgvector\n")
            f.write(_ENV_FLAG + "\n")
        self.stdout.write(self.style.SUCCESS(
            f"Appended {_ENV_FLAG} to {env_path}. Restart workers to apply."
        ))

    def _detect_dimensions(self) -> int | None:
        from apps.siteconfig.models import AIEmbeddingStore

        # tenant-isolation-allow: AIEmbeddingStore is public schema; need first non-empty row only.
        row = AIEmbeddingStore.objects.filter(
            lifecycle_status="active"
        ).exclude(embedding=[]).only("embedding").first()
        if not row or not row.embedding:
            return None
        try:
            return len(row.embedding)
        except (TypeError, AttributeError):
            return None
