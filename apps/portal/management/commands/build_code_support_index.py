"""Build AST code support index JSON (batch 1335)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from services.ai.code_index import write_code_support_index


class Command(BaseCommand):
    help = "Parse apps/ and services/ Python AST into docs/generated/code_support_index.json."

    def handle(self, *args, **options):
        path = write_code_support_index()
        self.stdout.write(self.style.SUCCESS(f"Wrote {path}"))
