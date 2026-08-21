"""B2B procurement (rubric metric M33) — the supply side of the school OS.

The point of this module is that a purchase order is DERIVABLE, not guessed. A
``SupplyRequirement`` records one fact a school already knows — "this subject needs
N of this product per student" (safety goggles per chemistry student, a workbook per
literature student) — and ``academics.SubjectAssignment`` already knows which
classroom studies which subject in which term. ``people.Enrollment`` knows how many
students sit in that classroom. Multiply, net off what is already in
``schoolops.InventoryItem``, group by vendor, and the order writes itself.

TENANCY. Every model here carries a ``school`` FK, including ``PurchaseOrderLine``
and ``VendorProduct`` which could have reached their school through a parent. That
denormalisation is deliberate: the RLS policy in migration 0040 is a per-table
``school_id::text = current_setting('app.current_school_id')`` check, so a table
without its own ``school_id`` cannot be protected by it.

MONEY. Decimal everywhere, never float (``scripts/scan_money_float.py`` is a
zero-tolerance gate). Amounts are stored, not recomputed on read, so a historical
order still shows the price that was actually agreed.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models


class Vendor(models.Model):
    """A supplier a school can order from.

    ``is_certified`` is the platform's marker that this supplier has been vetted;
    it is deliberately a plain flag rather than a separate catalog table, because
    certification is a property of the vendor relationship, not a different kind of
    vendor. Uncertified vendors are still orderable — the flag informs the operator,
    it does not gate them.
    """

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="procurement_vendors"
    )
    name = models.CharField(max_length=255)
    is_certified = models.BooleanField(
        default=False,
        help_text="Vetted supplier. Shown to operators; does not restrict ordering.",
    )
    contact_email = models.EmailField(blank=True)
    currency = models.CharField(
        max_length=3,
        default="USD",
        help_text="ISO-4217 code the vendor prices in.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schoolops_vendor"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "name"], name="uniq_vendor_name_per_school"
            )
        ]

    def __str__(self) -> str:
        return self.name


class VendorProduct(models.Model):
    """One orderable line item in a vendor's catalog."""

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="procurement_products"
    )
    vendor = models.ForeignKey(
        Vendor, on_delete=models.CASCADE, related_name="products"
    )
    sku = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    unit = models.CharField(
        max_length=32, default="each", help_text="each / box / pack / litre …"
    )
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schoolops_vendorproduct"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["vendor", "sku"], name="uniq_product_sku_per_vendor"
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.sku})"


class SupplyRequirement(models.Model):
    """THE CLASS CONFIGURATION: what one subject needs, per student.

    This is the row that makes M33 auto-generation honest. Without it a "purchase
    order generator" is just a basket; with it the quantity is derived from the
    timetable the school already maintains.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="procurement_requirements",
    )
    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.CASCADE,
        related_name="supply_requirements",
    )
    product = models.ForeignKey(
        VendorProduct, on_delete=models.PROTECT, related_name="supply_requirements"
    )
    quantity_per_student = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text="Units of this product each enrolled student needs.",
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schoolops_supplyrequirement"
        ordering = ["subject__name", "product__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "subject", "product"],
                name="uniq_requirement_per_subject_product",
            )
        ]

    def __str__(self) -> str:
        return f"{self.subject} → {self.product} ×{self.quantity_per_student}/student"


class PurchaseOrder(models.Model):
    """A tenant-scoped order against one vendor.

    Totals are STORED. Recomputing them on read would silently rewrite history the
    first time a vendor changed a price or a tax rate moved.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        RECEIVED = "RECEIVED", "Received"
        CANCELLED = "CANCELLED", "Cancelled"

    class Source(models.TextChoices):
        CLASS_CONFIG = "CLASS_CONFIG", "Auto-generated from class configuration"
        MANUAL = "MANUAL", "Created by hand"

    school = models.ForeignKey(
        "schools.School", on_delete=models.CASCADE, related_name="purchase_orders"
    )
    vendor = models.ForeignKey(
        Vendor, on_delete=models.PROTECT, related_name="purchase_orders"
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT
    )
    source = models.CharField(
        max_length=16, choices=Source.choices, default=Source.MANUAL
    )
    currency = models.CharField(max_length=3, default="USD")
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    tax_rate = models.DecimalField(
        max_digits=6,
        decimal_places=4,
        default=Decimal("0.0000"),
        help_text="Resolved at generation time via apps.billing.tax_engine.",
    )
    tax_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "schoolops"
        db_table = "schoolops_purchaseorder"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["school", "status"], name="idx_po_school_status"
            )
        ]

    def __str__(self) -> str:
        return f"PO-{self.pk} {self.vendor_id} {self.status}"

    @property
    def counts_toward_gmv(self) -> bool:
        """Drafts and cancellations are not gross merchandise value.

        GMV that counted drafts would be a vanity number: a draft is a proposal the
        school has not agreed to.
        """
        return self.status in {self.Status.SUBMITTED, self.Status.RECEIVED}


class PurchaseOrderLine(models.Model):
    """One product line on a purchase order.

    ``subject_assignment`` records WHICH class drove this line, so an operator
    reviewing a generated order can see "24 goggles because Chemistry / Form 4B"
    rather than an unexplained number.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        related_name="purchase_order_lines",
    )
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="lines"
    )
    product = models.ForeignKey(
        VendorProduct, on_delete=models.PROTECT, related_name="order_lines"
    )
    subject_assignment = models.ForeignKey(
        "academics.SubjectAssignment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_order_lines",
        help_text="The class configuration this quantity was derived from.",
    )
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        app_label = "schoolops"
        db_table = "schoolops_purchaseorderline"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.quantity} × {self.product_id}"
