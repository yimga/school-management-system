"""Help center route contracts — authenticated shell + next actions."""

from django.urls import reverse

from apps.feedback.models import FeedbackSubmission
from apps.portal.models_kb import FAQ, FAQCategory, KBArticle, KBCategory
from apps.siteconfig.models_feature_controls import GlobalSupportTicket

from .base import FeedbackHelpCenterTestCase


class FeedbackHelpCenterContractsTests(FeedbackHelpCenterTestCase):
    def test_help_center_redirects_anonymous(self):
        response = self.client.get(reverse("feedback:help_center"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_help_center_renders_for_staff(self):
        self.force_login_with_mfa(self.admin)
        response = self.client.get(reverse("feedback:help_center"))
        self.assertEqual(
            response.status_code,
            200,
            response.get("Location", getattr(response, "url", "")),
        )
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("help", body.lower())
        self.assertTrue(
            "feedback" in body.lower() or reverse("feedback:school_feedback") in body,
            "help center should bridge to feedback submission",
        )

    def test_help_center_role_surfaces_linked(self):
        self.force_login_with_mfa(self.teacher)
        response = self.client.get(reverse("feedback:help_center"))
        self.assertEqual(
            response.status_code,
            200,
            response.get("Location", getattr(response, "url", "")),
        )
        self.assertIn(reverse("feedback:teacher_feedback"), response.content.decode("utf-8", errors="replace"))

    def test_help_center_surfaces_kb_and_faq_matches(self):
        category = KBCategory.objects.create(name="Payments", slug="payments")
        KBArticle.objects.create(
            category=category,
            title="Fix payment receipts",
            slug="fix-payment-receipts",
            summary="How to find and download payment receipts.",
            content="payment receipt download finance",
            status="PUBLISHED",
            is_featured=True,
        )
        faq_category = FAQCategory.objects.create(name="Billing", slug="billing")
        FAQ.objects.create(
            category=faq_category,
            question="Where are receipts?",
            answer="Receipts are in the parent finance area.",
            tags="payment receipt billing",
            status="APPROVED",
        )
        self.force_login_with_mfa(self.admin)
        response = self.client.get(reverse("feedback:help_center"), {"q": "payment receipt"})
        self.assertEqual(
            response.status_code,
            200,
            response.get("Location", getattr(response, "url", "")),
        )
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn("Fix payment receipts", body)
        self.assertIn("Where are receipts?", body)

    def test_support_categories_create_support_ticket_from_feedback(self):
        self.force_login_with_mfa(self.admin)
        response = self.client.post(
            reverse("feedback:school_feedback"),
            {
                "form_kind": "feedback",
                "title": "Payment receipt missing",
                "category": FeedbackSubmission.Category.BILLING,
                "module": "finance",
                "route": "/parent/finance/",
                "severity": FeedbackSubmission.Severity.HIGH,
                "privacy_level": FeedbackSubmission.PrivacyLevel.SCHOOL_PRIVATE,
                "contact_preference": "email",
                "description": "Parent cannot download receipt after payment.",
                "source_channel": FeedbackSubmission.SourceChannel.HELP_CENTER,
                "source_url": reverse("feedback:help_center"),
            },
        )
        self.assertEqual(response.status_code, 302)
        feedback = FeedbackSubmission.objects.get(title="Payment receipt missing")
        self.assertTrue(feedback.support_escalated)
        self.assertTrue(feedback.related_support_ticket_id)
        ticket = GlobalSupportTicket.objects.get(pk=feedback.related_support_ticket_id)
        self.assertEqual(ticket.school, self.school_a)
        self.assertEqual(ticket.metadata["feedback_id"], feedback.pk)
