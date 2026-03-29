from django.test import TestCase


class SuperSupportTicketDetailPhaseHTests(TestCase):
    def test_skip_link_target_exists(self):
        from pathlib import Path

        from django.conf import settings

        path = Path(settings.BASE_DIR) / "templates" / "schools" / "super_support_ticket_detail.html"
        text = path.read_text(encoding="utf-8")
        self.assertIn('href="#support-ticket-detail-main"', text)
        self.assertIn('id="support-ticket-detail-main"', text)
