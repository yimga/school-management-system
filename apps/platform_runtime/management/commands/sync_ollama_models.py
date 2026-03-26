"""
Pull Ollama models needed by this deployment (env + optional registry), with allowlisting.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.core.management.base import BaseCommand

from apps.platform_runtime.ollama_model_sync import (
    collect_ollama_models_for_sync,
    run_ollama_pull,
)


class Command(BaseCommand):
    help = (
        "Run guarded `ollama pull` for OLLAMA_MODEL, Ollama embedding model (when backend is ollama), "
        "OLLAMA_SYNC_EXTRA_MODELS, and optionally AIModelRegistry active rows."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List models that would be pulled; do not invoke ollama.",
        )
        parser.add_argument(
            "--include-registry",
            action="store_true",
            default=None,
            help="Include AIModelRegistry active model_id values (default: env OLLAMA_SYNC_INCLUDE_REGISTRY=1).",
        )
        parser.add_argument(
            "--no-registry",
            action="store_true",
            help="Do not include AIModelRegistry (overrides env).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        no_registry = options["no_registry"]
        inc_reg = options["include_registry"]
        if no_registry:
            include_registry = False
        elif inc_reg is True:
            include_registry = True
        else:
            include_registry = os.getenv(
                "OLLAMA_SYNC_INCLUDE_REGISTRY", ""
            ).strip().lower() in ("1", "true", "yes")

        models = collect_ollama_models_for_sync(include_registry=include_registry)
        if not models:
            self.stdout.write(self.style.WARNING("No models to sync (after allowlist)."))
            return

        ollama_bin = (
            getattr(settings, "OLLAMA_CLI_PATH", None) or os.getenv("OLLAMA_CLI_PATH") or "ollama"
        ).strip() or "ollama"
        timeout = int(getattr(settings, "OLLAMA_PULL_TIMEOUT_SECONDS", 3600))

        for mid in models:
            self.stdout.write(f"Model: {mid}")
        if dry_run:
            self.stdout.write(self.style.SUCCESS("Dry run: no ollama pull executed."))
            return

        failures = 0
        for mid in models:
            self.stdout.write(f"Pulling {mid}...")
            code, tail = run_ollama_pull(mid, ollama_bin=ollama_bin, timeout=timeout)
            if code != 0:
                failures += 1
                self.stderr.write(self.style.ERROR(f"pull exit {code} for {mid}: {tail[-2000:]}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"Pulled {mid} (ok)."))
        if failures:
            self.stderr.write(
                self.style.ERROR(f"sync_ollama_models finished with {failures} failure(s).")
            )
        else:
            self.stdout.write(self.style.SUCCESS("sync_ollama_models completed."))
