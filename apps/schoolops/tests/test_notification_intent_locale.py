"""Notification-intent rendering must use the shared locale-aware email templates.

Before this, ``render_notification_intent`` returned a hardcoded English one-liner
for every ``notify.*`` intent and ignored the ``locale`` argument entirely — so a
French/Arabic parent got English even though the translated body already shipped on
disk (``templates/schoolops/email/locale/<code>/low_meal_balance.{txt,html}``). It
now delegates to ``apps.communication.email_locale.render_localized_email`` (the
same renderer the primary low-meal-balance sweep uses), falling back to the English
inline body only when no template exists for the key at all.

Pure rendering — no DB — so these are SimpleTestCase.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.schoolops.notification_intent import render_notification_intent

_MEAL_CTX = {
    "student_first_name": "Ada",
    "student_last_name": "Obi",
    "plan_label": "Gold",
    "balance_display": "500 XAF",
    "threshold_display": "1000 XAF",
}


class NotificationIntentLocaleTests(SimpleTestCase):
    def test_localized_template_wins_for_low_meal_balance_fr(self):
        # A locale template ships for low_meal_balance (fr): the recipient must get
        # the real French body + html, NOT the English inline one-liner.
        subject, body, html = render_notification_intent(
            template_key="low_meal_balance", locale="fr", context=_MEAL_CTX
        )
        self.assertIn("Bonjour", body)
        self.assertIn("solde du plan", body)
        self.assertIsNotNone(html)
        self.assertNotIn(
            "this is a notice regarding meal plan balance", body,
            msg="fr recipient must not receive the English inline body",
        )

    def test_unknown_locale_falls_back_to_english_template_not_inline(self):
        # A locale with no template (de) degrades to the EN *template* (the shared
        # renderer's fallback), not the terse inline one-liner.
        subject, body, html = render_notification_intent(
            template_key="low_meal_balance", locale="de", context=_MEAL_CTX
        )
        self.assertIn("courtesy notice", body)  # text unique to the en template
        self.assertIsNotNone(html)

    def test_template_less_key_uses_english_inline_body(self):
        # exam_readiness ships no locale template: fall back to the inline body,
        # html None (unchanged behaviour for keys without templates).
        subject, body, html = render_notification_intent(
            template_key="exam_readiness", locale="fr"
        )
        self.assertEqual(subject, "Exam readiness update")
        self.assertIn("exam readiness information is available", body)
        self.assertIsNone(html)

    def test_payment_received_stays_inline_with_none_html(self):
        # payment_received has no template on disk; the inline body (with the amount)
        # is returned and html is None — the contract the finance path relies on.
        subject, body, html = render_notification_intent(
            template_key="payment_received",
            locale="en",
            context={
                "student_name": "Ada",
                "amount": "100.00",
                "currency": "NGN",
                "reference": "INV-1",
            },
        )
        self.assertIn("Payment received", subject)
        self.assertIn("Ada", body)
        self.assertIsNone(html)

    def test_unknown_template_key_returns_generic_inline(self):
        subject, body, html = render_notification_intent(
            template_key="totally_unknown_key", locale="fr"
        )
        self.assertIn("totally_unknown_key", subject)
        self.assertIsNone(html)
