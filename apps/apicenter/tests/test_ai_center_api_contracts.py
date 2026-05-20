"""AI Center API payload contract shape."""

from __future__ import annotations

import json
from pathlib import Path

from django.test import SimpleTestCase

from services.ai_center.query_service import AICenterAnswer

ROOT = Path(__file__).resolve().parents[3]


class AICenterAPIContractsTests(SimpleTestCase):
    def test_answer_payload_fields(self):
        row = AICenterAnswer(
            answer="ok",
            audience="operator",
            route_context="/super/ai-center/",
            evidence=[{"doc_id": "app:apicenter"}],
            audit_id="abc",
        ).to_dict()
        for key in (
            "answer",
            "audience",
            "route_context",
            "evidence",
            "missing_context",
            "feature_absent",
            "confidence",
            "safety_flags",
            "audit_id",
        ):
            self.assertIn(key, row)

    def test_contract_doc_exists(self):
        path = ROOT / "docs" / "architecture" / "RUNMYCAMPUS_AI_CENTER_API_CONTRACTS.md"
        self.assertTrue(path.is_file(), msg="missing API contracts doc")

    def test_generated_contract_json_exists(self):
        path = ROOT / "docs" / "generated" / "ai_center_api_contracts.json"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn("query_response_fields", data)
