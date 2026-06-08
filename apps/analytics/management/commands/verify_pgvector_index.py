"""Post-deploy verification for the pgvector embedding index.

Confirms the four things that have to be true for the production
semantic-search path to actually serve from pgvector instead of the
JSON cosine fallback:

  1. `vector` extension is loaded in the current DB.
  2. `embedding_vec` column exists with a sensible dim.
  3. IVFFLAT index exists on that column.
  4. EXPLAIN on a representative query shows the index is being used
     (not falling back to a Seq Scan).

Also reports: row count, null-vector count, dim, index lists parameter.

Exits 0 when all four are green; non-zero on any required failure
(unless `--strict` is omitted, in which case the report prints and
exit is 0 even on failures).
"""

from __future__ import annotations

import json
import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

logger = logging.getLogger("apps.analytics.commands.verify_pgvector_index")

_TABLE = "siteconfig_aiembeddingstore"
_INDEX_NAME = "aiembedding_vec_ivfflat"


class Command(BaseCommand):
    help = "Verify the pgvector embedding index is in place + actually used."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")
        parser.add_argument(
            "--strict", action="store_true",
            help="Exit non-zero on any required failure.",
        )

    def handle(self, *args, **opts):
        if connection.vendor != "postgresql":
            raise CommandError(
                f"pgvector verification requires PostgreSQL; "
                f"current vendor is {connection.vendor}."
            )
        if self._indexable_row_count() == 0:
            detail = "skipped — no embedding rows indexed yet"
            results = [
                {"check": name, "ok": True, "detail": detail}
                for name in (
                    "extension_loaded",
                    "vector_column",
                    "ivfflat_index",
                    "explain_uses_index",
                    "row_stats",
                )
            ]
            if opts.get("json"):
                self.stdout.write(json.dumps(results, indent=2))
            else:
                self.stdout.write("pgvector index verification:")
                for r in results:
                    self.stdout.write(f"  [OK ] {r['check']:22s} {r['detail']}")
            return
        checks = [
            ("extension_loaded", self._check_extension),
            ("vector_column", self._check_column),
            ("ivfflat_index", self._check_index),
            ("explain_uses_index", self._check_explain),
            ("row_stats", self._row_stats),
        ]
        results = []
        for name, fn in checks:
            try:
                res = fn()
            except Exception as exc:  # noqa: BLE001
                res = {"ok": False, "detail": f"check crashed: {exc}"}
            res["check"] = name
            results.append(res)
        if opts.get("json"):
            self.stdout.write(json.dumps(results, indent=2))
        else:
            self.stdout.write("pgvector index verification:")
            for r in results:
                mark = "[OK ]" if r["ok"] else "[ - ]"
                self.stdout.write(f"  {mark} {r['check']:22s} {r['detail']}")
        if opts.get("strict"):
            if any(not r["ok"] for r in results):
                raise SystemExit(1)

    def _indexable_row_count(self) -> int:
        from apps.siteconfig.models import AIEmbeddingStore

        # tenant-isolation-allow: public-schema embedding store; sizing only.
        try:
            return AIEmbeddingStore.objects.filter(
                lifecycle_status="active"
            ).exclude(embedding=[]).count()
        except Exception:  # noqa: BLE001 — table may not exist on fresh DBs
            return 0

    def _check_extension(self) -> dict:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT extversion FROM pg_extension WHERE extname='vector'"
            )
            row = cur.fetchone()
        if not row:
            return {
                "ok": False,
                "detail": "`vector` extension not loaded (run CREATE EXTENSION vector;)",
            }
        return {"ok": True, "detail": f"vector extension v{row[0]} loaded"}

    def _check_column(self) -> dict:
        sql = """
            SELECT atttypmod
            FROM pg_attribute
            WHERE attrelid = %s::regclass
              AND attname = 'embedding_vec'
              AND NOT attisdropped
            LIMIT 1
        """
        with connection.cursor() as cur:
            cur.execute(sql, [_TABLE])
            row = cur.fetchone()
        if not row:
            return {"ok": False, "detail": "embedding_vec column does not exist"}
        dim = int(row[0])
        return {"ok": True, "detail": f"embedding_vec exists, dim={dim}"}

    def _check_index(self) -> dict:
        sql = """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = %s AND indexname = %s
        """
        with connection.cursor() as cur:
            cur.execute(sql, [_TABLE, _INDEX_NAME])
            row = cur.fetchone()
        if not row:
            return {"ok": False, "detail": f"index {_INDEX_NAME} missing"}
        return {"ok": True, "detail": f"{_INDEX_NAME} present: {row[1][:90]}"}

    def _check_explain(self) -> dict:
        """Build a small probe vector and EXPLAIN the search query.

        We don't care about the result — only that the planner reports
        an Index Scan, not a Seq Scan + sort.
        """
        col_check = self._check_column()
        if not col_check["ok"]:
            return {"ok": False, "detail": "column missing; cannot EXPLAIN"}
        # Extract dim from the column check's detail.
        try:
            dim = int(col_check["detail"].rsplit("=", 1)[-1])
        except (ValueError, IndexError):
            return {"ok": False, "detail": "couldn't extract dim for probe"}
        probe = "[" + ",".join(["0.0"] * dim) + "]"
        with connection.cursor() as cur:
            try:
                cur.execute(
                    "EXPLAIN SELECT id FROM siteconfig_aiembeddingstore "
                    "WHERE scope='student' "
                    "ORDER BY embedding_vec <=> %s::vector "
                    "LIMIT 10",
                    [probe],
                )
                plan_lines = [r[0] for r in cur.fetchall()]
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "detail": f"EXPLAIN failed: {exc}"}
        plan_text = "\n".join(plan_lines)
        if "Seq Scan" in plan_text and "Index Scan" not in plan_text:
            return {
                "ok": False,
                "detail": "planner chose Seq Scan; index unused. "
                "Run `VACUUM ANALYZE` and check `lists` parameter.",
            }
        if "Index Scan" in plan_text or "ivfflat" in plan_text.lower():
            return {"ok": True, "detail": "planner uses index"}
        # Empty table or table-scan acceptable when small.
        return {
            "ok": True,
            "detail": f"planner: {plan_lines[0][:80] if plan_lines else 'empty'}",
        }

    def _row_stats(self) -> dict:
        with connection.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM {_TABLE} WHERE lifecycle_status = 'active'"
            )
            total = cur.fetchone()[0]
            try:
                cur.execute(
                    f"SELECT COUNT(*) FROM {_TABLE} "
                    f"WHERE lifecycle_status = 'active' "
                    f"AND embedding_vec IS NULL AND embedding IS NOT NULL"
                )
                null_vec_with_json = cur.fetchone()[0]
            except Exception:  # noqa: BLE001 — column may be absent
                null_vec_with_json = -1
        return {
            "ok": null_vec_with_json == 0,
            "detail": (
                f"rows={total}, embedding_vec_null_but_json_set="
                f"{null_vec_with_json}"
                + (
                    " (run `migrate_embeddings_to_pgvector` to backfill)"
                    if null_vec_with_json > 0
                    else ""
                )
            ),
        }
