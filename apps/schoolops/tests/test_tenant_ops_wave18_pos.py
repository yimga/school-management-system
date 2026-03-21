"""Wave 18: POS stub ops module."""

import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase

from apps.schoolops.models import InventoryItem, PosSaleLine
from apps.schoolops.views_tenant_ops import ops_pos
from apps.schools.models import School

User = get_user_model()


class TenantOpsWave18PosTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="POS School",
            slug=f"pos-{uuid.uuid4().hex[:10]}",
            subdomain=f"pos-{uuid.uuid4().hex[:10]}",
            features={"pos_stub": True},
        )
        self.admin = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:8]}",
            email="a@p.test",
            password="x",
            role=User.Role.ADMIN,
        )

    def _req(self, method, path, data=None):
        if method == "GET":
            r = self.factory.get(path)
        else:
            r = self.factory.post(path, data or {})
        r.user = self.admin
        r.school = self.school
        SessionMiddleware(lambda x: None).process_request(r)
        r.session.save()
        setattr(r, "_messages", FallbackStorage(r))
        return r

    def test_record_sale_line(self):
        r = ops_pos(
            self._req(
                "POST",
                "/p/",
                {
                    "item_label": "Snack pack",
                    "quantity": "2",
                    "unit_price": "1.50",
                    "payment_method": "cash",
                },
            )
        )
        self.assertEqual(r.status_code, 302)
        line = PosSaleLine.objects.get(school=self.school)
        self.assertEqual(line.quantity, 2)
        self.assertEqual(line.line_total, Decimal("3.00"))

    def test_pos_feature_off_403(self):
        self.school.features = {"pos_stub": False}
        self.school.save(update_fields=["features"])
        self.assertEqual(ops_pos(self._req("GET", "/p/")).status_code, 403)

    def test_pos_links_inventory_when_enabled(self):
        self.school.features = {"pos_stub": True, "inventory": True}
        self.school.save(update_fields=["features"])
        inv = InventoryItem.objects.create(
            school=self.school, name="Notebook", quantity=40
        )
        r = ops_pos(
            self._req(
                "POST",
                "/p/",
                {
                    "inventory_item_id": str(inv.pk),
                    "unit_price": "2.00",
                    "payment_method": "cash",
                },
            )
        )
        self.assertEqual(r.status_code, 302)
        line = PosSaleLine.objects.get(school=self.school)
        self.assertEqual(line.inventory_item_id, inv.pk)
        self.assertEqual(line.item_label, "Notebook")
        inv.refresh_from_db()
        self.assertEqual(inv.quantity, 39)

    def test_pos_insufficient_inventory_blocks_sale(self):
        self.school.features = {"pos_stub": True, "inventory": True}
        self.school.save(update_fields=["features"])
        inv = InventoryItem.objects.create(
            school=self.school, name="Single", quantity=1
        )
        r = ops_pos(
            self._req(
                "POST",
                "/p/",
                {
                    "inventory_item_id": str(inv.pk),
                    "quantity": "3",
                    "unit_price": "1.00",
                    "payment_method": "cash",
                },
            )
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(PosSaleLine.objects.filter(school=self.school).exists())
        inv.refresh_from_db()
        self.assertEqual(inv.quantity, 1)

    def test_pos_sales_tax_snapshot_and_gross(self):
        r = ops_pos(
            self._req(
                "POST",
                "/p/",
                {
                    "item_label": "Uniform shirt",
                    "quantity": "2",
                    "unit_price": "10.00",
                    "tax_rate_percent": "7.5",
                    "payment_method": "card",
                },
            )
        )
        self.assertEqual(r.status_code, 302)
        line = PosSaleLine.objects.get(school=self.school)
        self.assertEqual(line.line_total, Decimal("20.00"))
        self.assertEqual(line.tax_rate_percent, Decimal("7.5"))
        self.assertEqual(line.tax_amount, Decimal("1.50"))
        self.assertEqual(line.grand_total, Decimal("21.50"))
