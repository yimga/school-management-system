from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from services.tenant_rag_bundle import (
    TenantRAGBundleError,
    export_tenant_rag_bundle,
)


class Command(BaseCommand):
    help = "Export a signed, tenant-bound AIEmbeddingStore bundle."

    def add_arguments(self, parser):
        parser.add_argument("--school", required=True, help="School UUID.")
        parser.add_argument("--output", required=True, help="Destination JSON file.")
        parser.add_argument(
            "--scope",
            action="append",
            default=[],
            help="Scope to include; repeat for multiple scopes.",
        )

    def handle(self, *args, **options):
        try:
            bundle = export_tenant_rag_bundle(
                options["school"],
                scopes=options["scope"],
            )
        except TenantRAGBundleError as exc:
            raise CommandError(str(exc)) from exc
        output = Path(options["output"]).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(bundle, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {bundle['record_count']} records to {output}."
            )
        )
