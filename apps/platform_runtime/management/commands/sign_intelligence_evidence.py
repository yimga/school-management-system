from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.platform_runtime.intelligence_promotion import (
    STAGE_RANK,
    load_catalog,
    sign_external_evidence_body,
    verify_external_evidence,
)


class Command(BaseCommand):
    help = "Sign an operator-reviewed intelligence promotion evidence body."

    def add_arguments(self, parser):
        parser.add_argument("--body", required=True)
        parser.add_argument("--output", required=True)

    def handle(self, *args, **options):
        body_path = Path(options["body"])
        body = json.loads(body_path.read_text(encoding="utf-8"))
        if not isinstance(body, dict):
            raise CommandError("evidence body must be a JSON object")
        try:
            envelope = sign_external_evidence_body(body)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        catalog = load_catalog()
        feature_ids = {
            str(row.get("feature_id") or "") for row in catalog["features"]
        }
        if body.get("feature_id") not in feature_ids:
            raise CommandError("evidence body feature_id is not in the catalog")
        approved_stage = str(body.get("approved_stage") or "")
        if approved_stage not in STAGE_RANK:
            raise CommandError("evidence body approved_stage is invalid")
        _rows, errors = verify_external_evidence(
            envelope,
            feature_id=str(body.get("feature_id") or ""),
            target_stage=approved_stage,
            allowed_dimensions=set(catalog["evidence_dimensions"]),
        )
        if errors:
            raise CommandError("; ".join(errors))
        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(envelope, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.stdout.write(
            self.style.SUCCESS(f"Signed intelligence evidence: {output}")
        )
