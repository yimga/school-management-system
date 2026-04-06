from unittest.mock import patch

from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.portal.support_ai_context import build_kb_context_block
from apps.portal.tasks import apply_support_ticket_ai_triage
from apps.schools.models import School
from apps.siteconfig.models_feature_controls import GlobalSupportTicket


class SupportAiContextTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Ctx School",
            slug="ctx-school",
            subdomain="ctx-school",
            is_active=True,
        )

    @override_settings(SUPPORT_AI_KB_CONTEXT=False)
    def test_kb_context_disabled_returns_empty(self):
        self.assertEqual(
            build_kb_context_block("Subject", "Body text here", self.school),
            "",
        )

    def test_no_school_returns_empty(self):
        self.assertEqual(build_kb_context_block("Subject", "Body text here", None), "")

    def test_no_tenant_client_returns_empty(self):
        # No django-tenants Client row → no schema for KB lookup
        self.assertEqual(
            build_kb_context_block("Password reset", "help with login", self.school),
            "",
        )


class ApplySupportTicketAiTriageTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Triage School",
            slug="triage-school",
            subdomain="triage-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="triage-user",
            password="pass",
        )
        self.user.role = "ADMIN"
        self.user.save(update_fields=["role"])
        self.ticket = GlobalSupportTicket.objects.create(
            school=self.school,
            user=self.user,
            subject="Need help",
            body="Printer issue",
            metadata={"country_code": "CM"},
        )

    @patch("apps.portal.ai_provider.suggest_support_ticket_response")
    def test_task_persists_ai_triage_metadata(self, mock_suggest):
        mock_suggest.return_value = (
            {
                "category": "IT",
                "priority": "NORMAL",
                "suggested_reply": "Try power cycle.",
            },
            {"gateway": True},
        )
        out = apply_support_ticket_ai_triage(str(self.ticket.pk))
        self.assertTrue(out.get("ok"))
        self.assertEqual(mock_suggest.call_args.kwargs["user_id"], self.user.pk)
        self.assertEqual(mock_suggest.call_args.kwargs["role"], "ADMIN")
        self.ticket.refresh_from_db()
        triage = self.ticket.metadata.get("ai_triage")
        self.assertIsInstance(triage, dict)
        self.assertEqual(triage["suggestions"]["category"], "IT")
        self.assertEqual(triage["suggested_reply_preview"], "Try power cycle.")
        self.assertTrue(triage["gateway"].get("gateway"))

    def test_task_invalid_uuid(self):
        out = apply_support_ticket_ai_triage("not-a-uuid")
        self.assertFalse(out.get("ok"))
