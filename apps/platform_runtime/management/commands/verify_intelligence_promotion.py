from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.platform_runtime.intelligence_promotion import (
    STAGE_SCOPE,
    evaluate_catalog,
    evaluate_promotion,
)


class Command(BaseCommand):
    help = "Evaluate fail-closed intelligence feature promotion evidence."

    def add_arguments(self, parser):
        parser.add_argument("--feature")
        parser.add_argument(
            "--stage",
            choices=tuple(STAGE_SCOPE),
            default="repository_verified",
        )
        parser.add_argument("--evidence-file")
        parser.add_argument("--write-report")
        parser.add_argument("--strict", action="store_true")

    def handle(self, *args, **options):
        feature_id = (options.get("feature") or "").strip()
        evidence = None
        if options.get("evidence_file"):
            evidence = json.loads(
                Path(options["evidence_file"]).read_text(encoding="utf-8")
            )
        if evidence and not feature_id:
            raise CommandError("--evidence-file requires --feature")

        if feature_id:
            report = evaluate_promotion(
                feature_id,
                target_stage=options["stage"],
                external_evidence=evidence,
            )
            blocked = 0 if report["eligible"] else 1
        else:
            report = evaluate_catalog(target_stage=options["stage"])
            blocked = report["blocked_count"]

        text = json.dumps(report, indent=2, sort_keys=True)
        self.stdout.write(text)
        if options.get("write_report"):
            path = Path(options["write_report"])
            if not path.is_absolute():
                from django.conf import settings

                path = Path(settings.BASE_DIR) / path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text + "\n", encoding="utf-8")
        if options["strict"] and blocked:
            raise SystemExit(1)
