"""Configure hub exposes tenant diagnostics entry."""

from django.test import SimpleTestCase
from django.urls import reverse

from apps.portal.views_configure import _build_catalog


class ConfigureHubZeroTicketTests(SimpleTestCase):
    def test_catalog_includes_tenant_diagnostics(self):
        zero_ticket_url = reverse("siteconfig:zero_ticket_hub")
        found = any(
            entry.url == zero_ticket_url
            for category in _build_catalog()
            for entry in category.entries
        )
        self.assertTrue(found, "zero_ticket_hub missing from configure catalog")
