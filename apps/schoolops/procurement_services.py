"""Derive purchase orders from class configuration (rubric metric M33).

The whole claim of M33 is that an order is DERIVED, not typed in. The chain is:

    SupplyRequirement  "Chemistry needs 1 goggle per student"
      × SubjectAssignment  "Chemistry is taught to Form 4B this term"
      × Enrollment(ACTIVE)  "Form 4B has 24 students"
      − InventoryItem       "we already hold 6 goggles"
      → PurchaseOrderLine   "order 18, because Chemistry / Form 4B"

Every quantity therefore traces to a row the school already maintains, and each line
keeps the ``subject_assignment`` that produced it so an operator can see *why*.

Money is Decimal end to end (``scripts/scan_money_float.py`` is zero-tolerance) and
tax comes from ``apps.billing.tax_engine``, not a hardcoded rate.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction

_CENTS = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    """Round to 2dp the way an invoice does, never with float()."""
    return Decimal(value).quantize(_CENTS, rounding=ROUND_HALF_UP)


def _active_enrolment_count(school, classroom_id, academic_year_id) -> int:
    """Students sitting in one classroom for one year.

    Enrollment is the source of truth; ``StudentProfile.classroom`` is only a
    synchronised projection of it, so counting profiles would drift the moment a
    rollover was mid-flight.
    """
    from apps.people.models import Enrollment

    return Enrollment.objects.filter(
        school=school,
        classroom_id=classroom_id,
        academic_year_id=academic_year_id,
        status=Enrollment.Status.ACTIVE,
    ).count()


def _on_hand(school, product_name: str) -> int:
    """Units already in stock, matched by name.

    Deliberately conservative: an inventory item is only netted off when its name
    matches the catalog product exactly. Guessing a fuzzy match here would silently
    under-order, which is the one failure mode a school cannot recover from on the
    morning a lab starts.
    """
    from apps.schoolops.models import InventoryItem

    row = InventoryItem.objects.filter(school=school, name__iexact=product_name).first()
    return int(row.quantity or 0) if row else 0


def compute_required_quantities(school, *, academic_year=None, term=None) -> dict:
    """Return ``{product_id: {"quantity": int, "assignment": SubjectAssignment}}``.

    Pure computation — reads only, writes nothing, so it can back a "what would this
    order?" preview as safely as the generator itself.
    """
    from apps.academics.models import SubjectAssignment
    from apps.schoolops.models import SupplyRequirement

    requirements = list(
        SupplyRequirement.objects.filter(
            school=school, is_active=True, product__is_active=True
        ).select_related("product", "product__vendor", "subject")
    )
    if not requirements:
        return {}

    by_subject = defaultdict(list)
    for req in requirements:
        by_subject[req.subject_id].append(req)

    assignments = SubjectAssignment.objects.filter(
        school=school, subject_id__in=list(by_subject.keys())
    ).select_related("classroom", "academic_year")
    if academic_year is not None:
        assignments = assignments.filter(academic_year=academic_year)
    if term is not None:
        assignments = assignments.filter(term=term)

    needed: dict[int, dict] = {}
    for assignment in assignments:
        head_count = _active_enrolment_count(
            school, assignment.classroom_id, assignment.academic_year_id
        )
        if head_count <= 0:
            continue
        for req in by_subject[assignment.subject_id]:
            units = int(
                (req.quantity_per_student * head_count).to_integral_value(
                    rounding=ROUND_HALF_UP
                )
            )
            if units <= 0:
                continue
            slot = needed.setdefault(
                req.product_id,
                {"quantity": 0, "assignment": assignment, "product": req.product},
            )
            slot["quantity"] += units
    return needed


@transaction.atomic
def generate_purchase_orders_from_class_config(
    school, *, academic_year=None, term=None
):
    """Create DRAFT purchase orders for what the timetable implies is missing.

    Returns the list of created orders (empty when nothing is short). Orders are
    grouped per vendor because a school places one order with one supplier, not one
    order per product. Always DRAFT: this function proposes, a human commits.
    """
    from apps.billing.tax_engine import resolve_tax_rate
    from apps.schoolops.models import PurchaseOrder, PurchaseOrderLine

    needed = compute_required_quantities(
        school, academic_year=academic_year, term=term
    )
    if not needed:
        return []

    by_vendor = defaultdict(list)
    for product_id, slot in needed.items():
        product = slot["product"]
        shortfall = slot["quantity"] - _on_hand(school, product.name)
        if shortfall <= 0:
            continue
        by_vendor[product.vendor_id].append((product, shortfall, slot["assignment"]))

    country = (getattr(school, "country_code", "") or "").upper()
    tax_rate = resolve_tax_rate(country) if country else Decimal("0")

    orders = []
    for vendor_id, rows in by_vendor.items():
        vendor = rows[0][0].vendor
        order = PurchaseOrder.objects.create(
            school=school,
            vendor=vendor,
            status=PurchaseOrder.Status.DRAFT,
            source=PurchaseOrder.Source.CLASS_CONFIG,
            currency=vendor.currency,
            tax_rate=tax_rate,
        )
        subtotal = Decimal("0.00")
        for product, quantity, assignment in rows:
            line_total = _money(product.unit_price * quantity)
            PurchaseOrderLine.objects.create(
                school=school,
                purchase_order=order,
                product=product,
                subject_assignment=assignment,
                quantity=quantity,
                unit_price=product.unit_price,
                line_total=line_total,
            )
            subtotal += line_total
        order.subtotal = _money(subtotal)
        order.tax_amount = _money(order.subtotal * tax_rate)
        order.total = _money(order.subtotal + order.tax_amount)
        order.save(update_fields=["subtotal", "tax_amount", "total"])
        orders.append(order)
    return orders


def tenant_gmv(school) -> Decimal:
    """Gross merchandise value: committed orders only.

    Drafts are excluded on purpose — counting proposals a school never agreed to
    would make GMV a number that flatters the platform instead of describing it.
    """
    from django.db.models import Sum

    from apps.schoolops.models import PurchaseOrder

    total = PurchaseOrder.objects.filter(
        school=school,
        status__in=[PurchaseOrder.Status.SUBMITTED, PurchaseOrder.Status.RECEIVED],
    ).aggregate(total=Sum("total"))["total"]
    return _money(total or Decimal("0.00"))
