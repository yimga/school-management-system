"""Wizard token humanization + MFA channel resolver (no DB).

Covers the "raw i18n token" bug where the MFA setup wizard rendered
``wizards.mfa_setup.step.choose_channel.label`` literally and showed
"No options available." because the step had no options_resolver.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.setup_studio.wizard_labels import humanize_wizard_token


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
