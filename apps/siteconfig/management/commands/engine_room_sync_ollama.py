"""
Engine room: HTTP pull + smoke-test + hot-swap active Ollama model pointer.
Complements platform_runtime.sync_ollama_models (CLI pull).
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from services.ai.lifecycle import OllamaModelLifecycleManager


class Command(BaseCommand):
    help = "Pull (via Ollama HTTP API), smoke-test, and activate OLLAMA_MODEL for first-line support."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-pull",
            action="store_true",
            help="Verify local tags only; do not POST /api/pull.",
        )

    def handle(self, *args, **options):
        mgr = OllamaModelLifecycleManager()
        report = mgr.check_and_update_model(pull_if_missing=not options["no_pull"])
        if report.get("healthy"):
            self.stdout.write(
                self.style.SUCCESS(
                    f"Engine room active model: {report.get('active_model')} "
                    f"(swapped={report.get('swapped')}, ms={report.get('latency_ms')})"
                )
            )
            return
        rolled = mgr.rollback_to_previous()
        self.stderr.write(
            self.style.ERROR(
                f"Update failed ({report.get('error')}); active pointer rolled back to {rolled}"
            )
        )
