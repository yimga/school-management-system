"""Wizard token humanization + MFA channel resolver (no DB).

Covers the "raw i18n token" bug where the MFA setup wizard rendered
``wizards.mfa_setup.step.choose_channel.label`` literally and showed
"No options available." because the step had no options_resolver.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.setup_studio.wizard_labels import (
    humanize_wizard_error,
    humanize_wizard_token,
)


class HumanizeWizardTokenTests(SimpleTestCase):
    def test_synthesized_slug_is_humanized(self):
        self.assertEqual(
            humanize_wizard_token("wizards.mfa_setup.step.choose_channel.label"),
            "Choose Channel",
        )

    def test_acronyms_are_uppercased(self):
        self.assertEqual(
            humanize_wizard_token("wizards.mfa_setup.step.sms_verify.label"),
            "SMS Verify",
        )
        self.assertEqual(
            humanize_wizard_token("wizards.mfa_setup.step.scan_qr.label"),
            "Scan QR",
        )

    def test_description_suffix_stripped(self):
        self.assertEqual(
            humanize_wizard_token(
                "wizards.mfa_setup.step.choose_channel.description"
            ),
            "Choose Channel",
        )

    def test_human_label_passes_through_unchanged(self):
        # Resolver-supplied labels (the convention) must never be mangled.
        for label in ("Mother", "PowerSchool", "FACTS / RenWeb",
                      "Authenticator app (recommended)"):
            self.assertEqual(humanize_wizard_token(label), label)

    def test_non_string_is_empty(self):
        self.assertEqual(humanize_wizard_token(None), "")
        self.assertEqual(humanize_wizard_token(123), "")
        self.assertEqual(humanize_wizard_token(""), "")


class HumanizeWizardErrorTests(SimpleTestCase):
    """Validator error tokens must render as real sentences, never raw slugs.

    Bug (2026-06-17 LOW-polish sweep): every input partial rendered
    ``{{ errors.value }}`` / ``{{ errors|dict_get:field.name }}`` straight off
    the validator, so a failed wizard step showed "wizards.errors.required"
    instead of a readable message.
    """

    def test_known_error_token_maps_to_sentence(self):
        self.assertEqual(
            humanize_wizard_error("wizards.errors.required"),
            "This field is required.",
        )
        self.assertEqual(
            humanize_wizard_error("wizards.errors.email_invalid"),
            "Enter a valid email address.",
        )

    def test_result_is_never_a_raw_slug(self):
        for token in (
            "wizards.errors.max_length",
            "wizards.errors.color_hex_invalid",
            "wizards.errors.pfx_magic_invalid",
            "wizards.errors.csv_header_required_missing",
        ):
            resolved = humanize_wizard_error(token)
            self.assertTrue(resolved)
            self.assertFalse(resolved.startswith("wizards."))

    def test_unmapped_token_falls_back_to_humanize(self):
        # An unmapped wizards.* slug still gets segment-humanized, not shown raw.
        self.assertEqual(
            humanize_wizard_error("wizards.errors.some_future_rule"),
            "Some Future Rule",
        )

    def test_human_message_passes_through(self):
        # A validator that already returned a human string is left intact.
        self.assertEqual(
            humanize_wizard_error("That date is in the past."),
            "That date is in the past.",
        )

    def test_non_string_is_empty(self):
        self.assertEqual(humanize_wizard_error(None), "")
        self.assertEqual(humanize_wizard_error(""), "")

    def test_every_validator_error_token_is_mapped(self):
        # Guard: every ``wizards.errors.*`` slug the validators can emit must have
        # an explicit message — a new validator error without one would silently
        # fall back to a terse segment-humanize.
        import re
        from pathlib import Path

        from apps.setup_studio import wizard_labels, wizard_validators

        source = Path(wizard_validators.__file__).read_text(encoding="utf-8")
        emitted = set(re.findall(r'"(wizards\.errors\.[a-z_]+)"', source))
        self.assertTrue(emitted, "expected to find error tokens in wizard_validators")
        missing = emitted - set(wizard_labels._WIZARD_ERROR_MESSAGES)
        self.assertEqual(
            missing, set(), f"unmapped validator error tokens: {sorted(missing)}"
        )


class MfaWizardResolverTests(SimpleTestCase):
    def test_mfa_wizard_has_human_label_not_slug(self):
        from apps.setup_studio import wizard_engine

        wizard = wizard_engine.get_wizard("mfa_setup")
        # label resolves to readable text, never a raw "wizards.*" slug.
        resolved = humanize_wizard_token(wizard.label_token)
        self.assertTrue(resolved)
        self.assertFalse(resolved.startswith("wizards."))

    def test_choose_channel_resolver_returns_three_channels(self):
        from apps.setup_studio import wizard_engine

        wizard = wizard_engine.get_wizard("mfa_setup")
        step = wizard.step_by_key("choose_channel")
        self.assertTrue(step.options_resolver)  # not None anymore
        options = wizard_engine.resolve_options(step, request=None, school=None)
        values = [o["value"] for o in options]
        # Values MUST match the step branches so routing works.
        self.assertEqual(values, ["totp", "sms", "passkey"])
        self.assertEqual(set(values), set(step.branches) - {"default"})
        for opt in options:
            self.assertTrue(opt["label_token"])
            self.assertFalse(str(opt["label_token"]).startswith("wizards."))
