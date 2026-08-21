"""M33 reachability — a feature nobody can reach is not shipped.

The service tests prove the arithmetic and the view tests prove the page works.
Neither notices that the page is linked from nowhere and that no operator can
create the rows the page computes over. That combination is how a feature passes
its whole test suite while being, in practice, dead.

Both assertions below fail on the commit that first added M33.
"""

from __future__ import annotations

from django.test import SimpleTestCase
from django.urls import set_urlconf

from config.admin import tenant_admin_site


class ProcurementIsReachableTests(SimpleTestCase):
    def setUp(self) -> None:
        set_urlconf("config.tenant_urls")

    def tearDown(self) -> None:
        set_urlconf(None)

    def test_ops_hub_offers_a_procurement_card(self):
        """The ops hub is the only nav that leads here; without a card, nothing does."""
        from apps.schoolops.views_tenant_ops import MODULE_CODES

        url_names = [url_name for _code, _label, url_name in MODULE_CODES]
        self.assertIn("accounts:ops_procurement", url_names)

    def test_procurement_models_are_registered_for_operators(self):
        """Vendors, products and supply requirements must be creatable.

        `generate_purchase_orders_from_class_config` reads SupplyRequirement. If a
        school cannot create one, the generator is correct and permanently
        returns [] -- the 'tables that ship empty' failure mode.
        """
        from apps.schoolops.models import (
            PurchaseOrder,
            SupplyRequirement,
            Vendor,
            VendorProduct,
        )

        for model in (Vendor, VendorProduct, SupplyRequirement, PurchaseOrder):
            with self.subTest(model=model.__name__):
                self.assertIn(
                    model,
                    tenant_admin_site._registry,
                    f"{model.__name__} is not registered on the tenant admin site, "
                    "so no operator can create or inspect its rows.",
                )
