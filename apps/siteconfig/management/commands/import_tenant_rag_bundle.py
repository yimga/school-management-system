from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from services.tenant_rag_bundle import (
    TenantRAGBundleError,
    import_tenant_rag_bundle,
)


class Command(BaseCommand):
    help = "Verify and import a signed tenant RAG bundle into AIEmbeddingStore."

    def add_arguments(self, parser):
        parser.add_argument("--school", required=True, help="Target school UUID.")
        parser.add_argument("--input", required=True, help="Source bundle JSON file.")

    def handle(self, *args, **options):
        source = Path(options["input"]).resolve()
        try:
            envelope = json.loads(source.read_text(encoding="utf-8"))
            summary = import_tenant_rag_bundle(
                envelope,
                expected_school_id=options["school"],
            )
        except (OSError, json.JSONDecodeError, TenantRAGBundleError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                "Tenant RAG import complete: "
                f"created={summary.created}, updated={summary.updated}, "
                f"skipped={summary.skipped}, tombstoned={summary.tombstoned}."
            )
        )
