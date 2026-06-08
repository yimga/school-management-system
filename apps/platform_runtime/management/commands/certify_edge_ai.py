from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from services.edge_model_certification import (
    benchmark_model,
    sign_evidence,
    verify_evidence,
)


class Command(BaseCommand):
    help = "Benchmark one cataloged Ollama model and write signed edge evidence."

    def add_arguments(self, parser):
        parser.add_argument("--model", required=True)
        parser.add_argument("--concurrency", type=int, default=1)
        parser.add_argument("--runs", type=int, default=3)
        parser.add_argument("--output", required=True)
        parser.add_argument("--strict-signing", action="store_true")

    def handle(self, *args, **options):
        body = benchmark_model(
            options["model"],
            concurrency=options["concurrency"],
            runs=options["runs"],
        )
        envelope = sign_evidence(body)
        if options["strict_signing"] and not verify_evidence(envelope):
            raise CommandError(
                "Set EDGE_MODEL_CERTIFICATION_SIGNING_KEY before strict certification."
            )
        output = Path(options["output"]).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(envelope, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        pilot_passed = bool(
            body.get("benchmark", {}).get("performance_gate_passed")
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Edge AI evidence written: {output} "
                f"(pilot_performance_passed={str(pilot_passed).lower()}, "
                "production_certified=false pending external drills)"
            )
        )
