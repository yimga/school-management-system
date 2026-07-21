"""Tier 0.1 — student PII must not reach an external LLM.

Guards three properties of ``services.ai_gateway`` / ``services.inference``:

1. The PII detector fails CLOSED — if it cannot be imported or it raises, the
   payload is assumed to be personal data and the external (premium) tier is
   denied.
2. An UNKNOWN sensitivity class denies premium; only an explicitly declared,
   allow-listed class permits it.
3. The bytes actually handed to the external transport are the REDACTED text —
   a student name and date of birth never leave the process verbatim.

Every test here is written to go red if the corresponding fix is reverted.
"""
from __future__ import annotations

import json
import sys
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from services.ai_gateway import (
    TaskType,
    _call_litellm,
    _data_tier_allows_premium,
    _payload_contains_pii,
    invoke,
    reset_ai_gateway_circuits,
)
from services.inference import (
    contains_hard_pii,
    iter_pii_values_in_metadata,
    redact_for_external_inference,
    redact_known_values,
    strip_pii_for_inference,
)

_LITELLM_OK_BODY = b'{"choices":[{"message":{"content":"Steady progress this term."}}]}'


class PayloadPiiDetectorFailsClosedTests(SimpleTestCase):
    """(a) redactor unavailable => assume PII => premium denied."""

    def test_detector_reports_pii_when_module_import_fails(self):
        with patch.dict(sys.modules, {"services.inference": None}):
            self.assertTrue(_payload_contains_pii("totally benign text"))

    def test_detector_reports_pii_when_detector_raises(self):
        with patch(
            "services.inference.contains_hard_pii", side_effect=RuntimeError("boom")
        ):
            self.assertTrue(_payload_contains_pii("totally benign text"))

    def test_premium_denied_when_redactor_import_fails(self):
        metadata = {"sensitivity_class": "low"}
        # Control: with the detector available this payload is allowed, so the
        # denial below is caused by the import failure and nothing else.
        self.assertTrue(
            _data_tier_allows_premium(
                metadata, prompt="Explain the grading scale", user_query="grading"
            )
        )
        with patch.dict(sys.modules, {"services.inference": None}):
            self.assertFalse(
                _data_tier_allows_premium(
                    metadata, prompt="Explain the grading scale", user_query="grading"
                )
            )

    def test_transport_refuses_to_send_when_redactor_import_fails(self):
        with override_settings(LITELLM_PROXY_URL="https://proxy.example/v1"):
            with patch.dict(sys.modules, {"services.inference": None}):
                with patch("services.ai_gateway.urllib.request.urlopen") as mock_open:
                    text, meta = _call_litellm("hello", metadata={})
        self.assertIsNone(text)
        self.assertEqual(meta.get("error"), "redaction_unavailable")
        mock_open.assert_not_called()


@override_settings(AI_GATEWAY_ENABLED=True, AI_ALLOW_RULES_FALLBACK=True)
class PremiumSensitivityGateTests(TestCase):
    """(c) unknown sensitivity class denies premium."""

    def setUp(self):
        reset_ai_gateway_circuits()

    @override_settings(AI_GATEWAY_TASK_TIERS={"general_chat": ["litellm", "rules"]})
    @patch(
        "services.ai_gateway._call_litellm",
        return_value=("premium answer", {"provider": "litellm", "tier": "litellm"}),
    )
    def test_missing_sensitivity_class_denies_premium(self, mock_litellm):
        _result, meta = invoke(
            TaskType.GENERAL_CHAT,
            "Summarise the timetable policy",
            user_query="timetable policy",
            metadata={"latency_target": 30},
        )
        self.assertEqual(meta.get("errors", {}).get("litellm"), "data_tier_disallowed")
        mock_litellm.assert_not_called()

    @override_settings(AI_GATEWAY_TASK_TIERS={"general_chat": ["litellm", "rules"]})
    @patch(
        "services.ai_gateway._call_litellm",
        return_value=("premium answer", {"provider": "litellm", "tier": "litellm"}),
    )
    def test_no_metadata_at_all_denies_premium(self, mock_litellm):
        _result, meta = invoke(
            TaskType.GENERAL_CHAT,
            "Summarise the timetable policy",
            user_query="timetable policy",
        )
        self.assertEqual(meta.get("errors", {}).get("litellm"), "data_tier_disallowed")
        mock_litellm.assert_not_called()

    @override_settings(AI_GATEWAY_TASK_TIERS={"general_chat": ["litellm", "rules"]})
    @patch(
        "services.ai_gateway._call_litellm",
        return_value=("premium answer", {"provider": "litellm", "tier": "litellm"}),
    )
    def test_unrecognised_sensitivity_class_denies_premium(self, mock_litellm):
        _result, meta = invoke(
            TaskType.GENERAL_CHAT,
            "Summarise the timetable policy",
            user_query="timetable policy",
            metadata={"sensitivity_class": "unspecified-by-caller"},
        )
        self.assertEqual(meta.get("errors", {}).get("litellm"), "data_tier_disallowed")
        mock_litellm.assert_not_called()

    @override_settings(AI_GATEWAY_TASK_TIERS={"general_chat": ["litellm", "rules"]})
    @patch(
        "services.ai_gateway._call_litellm",
        return_value=("premium answer", {"provider": "litellm", "tier": "litellm"}),
    )
    def test_declared_low_sensitivity_still_permits_premium(self, mock_litellm):
        """Positive control: the gate denies UNKNOWN, it is not a blanket deny."""
        result, meta = invoke(
            TaskType.GENERAL_CHAT,
            "Summarise the timetable policy",
            user_query="timetable policy",
            metadata={"sensitivity_class": "low"},
        )
        self.assertEqual(result, "premium answer")
        self.assertEqual(meta.get("tier"), "litellm")
        mock_litellm.assert_called_once()

    @override_settings(
        AI_GATEWAY_TASK_TIERS={"general_chat": ["litellm", "rules"]},
        AI_EXTERNAL_ALLOWED_SENSITIVITY_CLASSES=["public"],
    )
    @patch(
        "services.ai_gateway._call_litellm",
        return_value=("premium answer", {"provider": "litellm", "tier": "litellm"}),
    )
    def test_allowlist_is_deployment_configurable(self, mock_litellm):
        _result, meta = invoke(
            TaskType.GENERAL_CHAT,
            "Summarise the timetable policy",
            user_query="timetable policy",
            metadata={"sensitivity_class": "low"},
        )
        self.assertEqual(meta.get("errors", {}).get("litellm"), "data_tier_disallowed")
        mock_litellm.assert_not_called()

    def test_explicit_deny_paths_are_preserved(self):
        self.assertFalse(
            _data_tier_allows_premium({"sensitivity_class": "high"}, prompt="hi")
        )
        self.assertFalse(
            _data_tier_allows_premium(
                {"sensitivity_class": "low", "disallow_external_model": True},
                prompt="hi",
            )
        )
        self.assertFalse(
            _data_tier_allows_premium(
                {"sensitivity_class": "low"},
                prompt="mail me at head@example.org",
            )
        )


@override_settings(
    AI_GATEWAY_ENABLED=True,
    AI_ALLOW_RULES_FALLBACK=True,
    LITELLM_PROXY_URL="https://proxy.example/v1",
    LITELLM_API_KEY="secret-key",
    LITELLM_MODEL="test-model",
    AI_GATEWAY_TASK_TIERS={"report_card_comment": ["litellm", "rules"]},
)
class OutboundRedactionTests(TestCase):
    """(b) the bytes handed to the external transport carry neither name nor DOB."""

    def setUp(self):
        reset_ai_gateway_circuits()

    @staticmethod
    def _sent_body(mock_urlopen) -> str:
        request = mock_urlopen.call_args[0][0]
        raw = request.data
        assert isinstance(raw, bytes)
        return raw.decode("utf-8")

    @patch("services.ai_gateway.urllib.request.urlopen")
    def test_external_transport_receives_neither_name_nor_dob_iso(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value.read.return_value = (
            _LITELLM_OK_BODY
        )
        prompt = (
            "Write a report-card comment for Amara Okonkwo, date of birth "
            "2011-03-14, who improved in mathematics this term."
        )
        result, meta = invoke(
            TaskType.REPORT_CARD_COMMENT,
            prompt,
            user_query="report card comment",
            metadata={
                "sensitivity_class": "low",
                "student_name": "Amara Okonkwo",
                "date_of_birth": "2011-03-14",
                "school_name": "Bright Future Academy",
            },
        )
        self.assertEqual(result, "Steady progress this term.")
        self.assertEqual(meta.get("tier"), "litellm")
        mock_urlopen.assert_called_once()

        body = self._sent_body(mock_urlopen)
        for needle in ("Amara", "Okonkwo", "2011-03-14"):
            self.assertNotIn(needle, body)
        # The request really did carry the task (not an empty/blocked payload).
        self.assertIn("mathematics", body)
        sent = json.loads(body)
        self.assertNotIn("Okonkwo", sent["messages"][0]["content"])

    @patch("services.ai_gateway.urllib.request.urlopen")
    def test_external_transport_redacts_day_first_date_format(self, mock_urlopen):
        """Locale-neutral: DMY dates are handled, not just ISO/US ordering."""
        mock_urlopen.return_value.__enter__.return_value.read.return_value = (
            _LITELLM_OK_BODY
        )
        result, _meta = invoke(
            TaskType.REPORT_CARD_COMMENT,
            "Comment for Sofia Aguilar Reyes (born 14/03/2011) on her science work.",
            user_query="report card comment",
            metadata={
                "sensitivity_class": "low",
                "guardian_name": "Sofia Aguilar Reyes",
                "learner_dob": "14/03/2011",
            },
        )
        self.assertEqual(result, "Steady progress this term.")
        body = self._sent_body(mock_urlopen)
        for needle in ("Sofia", "Aguilar", "Reyes", "14/03/2011"):
            self.assertNotIn(needle, body)
        self.assertIn("science", body)

    @patch("services.ai_gateway.urllib.request.urlopen")
    def test_metadata_pii_field_list_is_deployment_extensible(self, mock_urlopen):
        mock_urlopen.return_value.__enter__.return_value.read.return_value = (
            _LITELLM_OK_BODY
        )
        with override_settings(AI_PII_METADATA_FIELDS=["house_tutor"]):
            invoke(
                TaskType.REPORT_CARD_COMMENT,
                "Comment prepared with Kwabena Mensah supervising the cohort.",
                user_query="report card comment",
                metadata={"sensitivity_class": "low", "house_tutor": "Kwabena Mensah"},
            )
        body = self._sent_body(mock_urlopen)
        self.assertNotIn("Kwabena", body)
        self.assertNotIn("Mensah", body)


class RedactionRegistryTests(SimpleTestCase):
    """services.inference — declarative, locale-extensible redaction."""

    def test_hard_identifiers_detected(self):
        self.assertTrue(contains_hard_pii("write to head@example.org"))
        self.assertTrue(contains_hard_pii("call +237 6 12 34 56 78 today"))

    def test_bare_date_is_redacted_but_is_not_a_hard_identifier(self):
        self.assertFalse(contains_hard_pii("term starts 2026-01-05"))
        self.assertIn("[date redacted]", strip_pii_for_inference("term starts 2026-01-05"))

    def test_metadata_walk_collects_personal_fields_and_skips_thing_names(self):
        values = iter_pii_values_in_metadata(
            {
                "student_name": "Amara Okonkwo",
                "school_name": "Bright Future Academy",
                "guardian": {"phone_number": "+44 7700 900123"},
                "tenant_id": "t-1",
            }
        )
        self.assertIn("Amara Okonkwo", values)
        self.assertIn("+44 7700 900123", values)
        self.assertNotIn("Bright Future Academy", values)

    def test_known_value_scrub_is_name_order_agnostic(self):
        out = redact_known_values("Okonkwo, Amara sat the exam", ["Amara Okonkwo"])
        self.assertNotIn("Amara", out)
        self.assertNotIn("Okonkwo", out)

    def test_extra_patterns_are_configurable_per_deployment(self):
        national_id = "AB-123456-C"
        self.assertIn(national_id, strip_pii_for_inference(f"id {national_id}"))
        with override_settings(
            AI_PII_REDACTION_PATTERNS=[
                {
                    "name": "national_id",
                    "pattern": r"\b[A-Z]{2}-\d{6}-[A-Z]\b",
                    "replacement": "[id redacted]",
                    "hard": True,
                }
            ]
        ):
            self.assertNotIn(national_id, strip_pii_for_inference(f"id {national_id}"))
            self.assertTrue(contains_hard_pii(f"id {national_id}"))

    def test_redact_for_external_inference_combines_both_layers(self):
        out = redact_for_external_inference(
            "Amara Okonkwo (2011-03-14) can be reached via head@example.org",
            {"student_name": "Amara Okonkwo"},
        )
        self.assertNotIn("Amara", out)
        self.assertNotIn("Okonkwo", out)
        self.assertNotIn("2011-03-14", out)
        self.assertNotIn("head@example.org", out)
