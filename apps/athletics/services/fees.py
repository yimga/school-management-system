"""Kit-fee invoicing for team memberships.

Raises a finance ``Invoice`` (+ ``InvoiceLine``) for a membership's team kit fee,
following the exact finance service pattern (ComplianceProfile resolution,
AR invoice, single line, ``recalculate_invoice``, best-effort event emit). All
money is ``Decimal`` — never float.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def _resolve_compliance_profile(school):
    """Resolve the finance ComplianceProfile for ``school`` (finance's pattern).

    Prefers the school's linked profile via effective site settings, falling
    back to the first active platform profile.
    """
    from apps.finance.models import ComplianceProfile
    from apps.siteconfig.config_service import get_effective_site_settings

    # config-resolver-allow: athletics-kit-fee-needs-compliance-profile-attribute-off-settings
    site = get_effective_site_settings(school=school)
    profile = getattr(site, "compliance_profile", None)
    if profile is not None:
        return profile
    # tenant-isolation-allow: compliance-profile-is-platform-global-no-tenant-fk
    return ComplianceProfile.objects.filter(is_active=True).first()


@transaction.atomic
def raise_kit_fee_invoice(*, membership, actor=None):
    """Raise an AR invoice for the membership team's mandatory kit fee.

    Resolves the first active + mandatory ``TeamKitFee`` for the team, creates
    an idempotent (per team+student) AR invoice with a single line, recalculates
    it, and best-effort emits ``invoice.created``. Raises ``ValueError`` when no
    kit fee or compliance profile is configured.
    """
    from apps.athletics.models import TeamKitFee
    from apps.finance.models import Invoice, InvoiceLine
    from apps.finance.services import recalculate_invoice

    school = membership.school
    kit_fee = (
        TeamKitFee.objects.filter(
            school=school,
            team_id=membership.team_id,
            is_active=True,
            is_mandatory=True,
        )
        .order_by("id")
        .first()
    )
    if kit_fee is None:
        raise ValueError("no active mandatory kit fee for this team")

    profile = _resolve_compliance_profile(school)
    if profile is None:
        raise ValueError("no compliance profile configured for finance")

    amount = Decimal(str(kit_fee.amount))
    reference = f"KIT-{membership.team_id}-{membership.student_id}"[:64]

    invoice, created = Invoice.objects.get_or_create(
        profile=profile,
        school=school,
        student_id=membership.student_id,
        invoice_type=Invoice.InvoiceType.AR,
        reference=reference,
        defaults={
            "status": Invoice.Status.ISSUED,
            "issued_date": timezone.now().date(),
            "total_amount": amount,
            "created_by": actor if getattr(actor, "pk", None) else None,
        },
    )

    if created:
        InvoiceLine.objects.create(
            invoice=invoice,
            description=kit_fee.label,
            quantity=Decimal("1.00"),
            unit_price=amount,
            amount=amount,
        )
        recalculate_invoice(invoice)
        _emit_invoice_created(invoice=invoice, school=school, membership=membership)

    return invoice


def _emit_invoice_created(*, invoice, school, membership) -> None:
    """Best-effort domain event emit (mirrors finance ``create_fee_invoices``)."""
    try:
        from apps.events.services import emit_event

        school_id = getattr(school, "id", None)
        emit_event(
            "invoice.created",
            {
                "invoice_id": str(invoice.id),
                "student_id": str(membership.student_id),
                "reference": invoice.reference or "",
                "source": "athletics_kit_fee",
            },
            school_id=school_id,
        )
    except (ImportError, AttributeError, TypeError, ValueError, KeyError) as exc:
        logger.debug("athletics kit-fee invoice.created emit skipped: %s", exc)


__all__ = ["raise_kit_fee_invoice"]
