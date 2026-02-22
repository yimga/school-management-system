from django.test import TestCase

from apps.portal.services import _communication_center
from apps.siteconfig.models import Integration, SiteSettings


class CommunicationCenterTests(TestCase):
    def setUp(self):
        Integration.objects.all().delete()
        site = SiteSettings.get_solo()
        site.company_phone = "+1 (222) 333-4444"
        site.company_email = "support@example.com"
        site.save()

    def test_whatsapp_phone_email_links_render(self):
        uid = id(self)
        Integration.objects.create(
            name="WhatsApp Support",
            slug="whatsapp-support-cc-%s" % uid,
            provider="other",
            enabled=True,
            config={"phone": "+1 800 555 0000"},
        )
        Integration.objects.create(
            name="Zoom Helpdesk",
            slug="zoom-helpdesk-cc-%s" % uid,
            provider="other",
            enabled=True,
            config={"url": "https://zoom.example.com/help"},
        )

        data = _communication_center()

        # Items include contact rows
        self.assertTrue(any(item["type"] == "phone" for item in data["items"]))
        self.assertTrue(any(item["type"] == "email" for item in data["items"]))
        self.assertTrue(any(item["type"] == "whatsapp" for item in data["items"]))

        # Links include normalized tel/mailto/wa.me actions
        urls = [link["url"] for link in data["links"]]
        self.assertIn("tel:+12223334444", urls)
        self.assertIn("mailto:support@example.com", urls)
        self.assertIn("https://wa.me/18005550000", urls)

        # WhatsApp action should be primary
        self.assertEqual(data["primary_action"]["url"], "https://wa.me/18005550000")
        self.assertIn("reminders", data["note"])

    def test_empty_contacts_returns_no_links(self):
        site = SiteSettings.get_solo()
        site.company_phone = ""
        site.company_email = ""
        site.whatsapp_support_number = ""
        setattr(site, "footer_whatsapp_url", "")
        site.save()
        Integration.objects.all().delete()

        data = _communication_center()

        self.assertEqual(data["items"], [])
        self.assertEqual(data["links"], [])
        self.assertIsNone(data["primary_action"])
