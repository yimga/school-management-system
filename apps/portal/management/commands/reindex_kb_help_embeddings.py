"""
Re-chunk and refresh KBArticle vector_embedding fields (help-center graft batch 1334).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.portal.kb_context import published_kb_queryset
from apps.portal.kb_embeddings import embedding_source_text, refresh_kb_article_embedding
from apps.portal.support_ingest import chunk_text_sliding_window


class Command(BaseCommand):
    help = "Refresh vector_embedding on published KB articles for support RAG/deflection."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="Max articles (0=all).")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        from services.ai_memory import get_embedding_for_text

        if not get_embedding_for_text("probe", max_tokens=8):
            self.stderr.write(
                self.style.ERROR("Embedding provider unavailable (Ollama or compatible).")
            )
            return
        qs = published_kb_queryset().order_by("-updated_at")
        limit = int(options.get("limit") or 0)
        if limit > 0:
            qs = qs[:limit]
        updated = 0
        dry = options.get("dry_run", False)
        for article in qs.iterator(chunk_size=100):
            parts = [embedding_source_text(article)]
            body = (getattr(article, "content", None) or "").strip()
            if body:
                parts.extend(chunk_text_sliding_window(body, chunk_tokens=500, overlap_tokens=50))
            text = "\n".join(p for p in parts if p).strip()
            if not text:
                continue
            if dry:
                updated += 1
                continue
            if refresh_kb_article_embedding(article, save=True):
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"KB embeddings refreshed: {updated} (dry_run={dry})"))
