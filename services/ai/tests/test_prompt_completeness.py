"""Audit: master prompt and payload assembly match the first-line support blueprint."""

from __future__ import annotations

from django.test import SimpleTestCase

from services.ai.prompts import (
    COMMAND_BAR_SNIPPET_HINT,
    ESCALATION_USER_MESSAGE,
    PLATFORM_ESCALATION_MESSAGE,
    PLATFORM_SRE_SYSTEM,
    TENANT_FIRST_LINE_SUPPORT_SYSTEM,
    assemble_ollama_payload,
    looks_like_hallucinated_fluff,
    validate_response_structure,
)


class PromptCompletenessTests(SimpleTestCase):
    def test_tenant_prompt_has_all_five_guardrails(self):
        blob = TENANT_FIRST_LINE_SUPPORT_SYSTEM
        for phrase in (
            "ABSOLUTE ANCHORING",
            "SYSTEM NAVIGATION PATHS",
            "PERMISSION-AWARE BOUNDARIES",
            "ZERO-FLUFF OUTPUT",
            "RESPONSE STRUCTURE",
        ):
            self.assertIn(phrase, blob)

    def test_tenant_prompt_has_full_response_headings_and_example(self):
        for heading in (
            "**Direct Answer**",
            "**Execution Path**",
            "**Action Steps**",
            "**System Bound**",
            "New Enrollment",
            "Commit Records",
        ):
            self.assertIn(heading, TENANT_FIRST_LINE_SUPPORT_SYSTEM)

    def test_escalation_strings_exact(self):
        self.assertIn("Escalate to Campus Helpdesk", ESCALATION_USER_MESSAGE)
        self.assertIn("operator helpdesk", PLATFORM_ESCALATION_MESSAGE)

    def test_assemble_payload_sections(self):
        payload = assemble_ollama_payload(
            system_prompt=TENANT_FIRST_LINE_SUPPORT_SYSTEM,
            user_context_block="[USER CURRENT CONTEXT]\nUser Role: Registrar",
            knowledge_snippets="- KB: scheduling steps",
            user_question="How do I add a class slot?",
        )
        for section in (
            TENANT_FIRST_LINE_SUPPORT_SYSTEM[:40],
            "[USER CURRENT CONTEXT]",
            "[RETRIEVED KNOWLEDGE BASE SNIPPETS]",
            "[USER QUESTION]",
            "How do I add a class slot?",
        ):
            self.assertIn(section, payload)

    def test_validate_good_structure(self):
        text = (
            "**Direct Answer**: Yes.\n"
            "**Execution Path**: **A > B**\n"
            "**Action Steps**:\n1. Click Save.\n"
        )
        ok, missing = validate_response_structure(text)
        self.assertTrue(ok)
        self.assertEqual(missing, [])

    def test_validate_escalation_always_ok(self):
        ok, _ = validate_response_structure(ESCALATION_USER_MESSAGE)
        self.assertTrue(ok)

    def test_fluff_detector(self):
        self.assertTrue(looks_like_hallucinated_fluff("Sure, I can help with that! Here is how..."))

    def test_platform_prompt_has_five_guardrails(self):
        for phrase in (
            "ABSOLUTE ANCHORING",
            "SYSTEM NAVIGATION PATHS",
            "PERMISSION-AWARE BOUNDARIES",
            "ZERO-FLUFF OUTPUT",
            "RESPONSE STRUCTURE",
        ):
            self.assertIn(phrase, PLATFORM_SRE_SYSTEM)

    def test_permission_denial_with_direct_answer_valid(self):
        denial = (
            "**Direct Answer**: As TEACHER, you do not possess ledger clearance.\n"
            "**Execution Path**: **Finance > Contact Bursar**\n"
            "**Action Steps**:\n1. Contact finance.\n"
        )
        ok, missing = validate_response_structure(denial)
        self.assertTrue(ok, missing)

    def test_command_bar_hint_present(self):
        self.assertIn("Command bar context", COMMAND_BAR_SNIPPET_HINT)
        self.assertIn("Direct Answer", COMMAND_BAR_SNIPPET_HINT)
