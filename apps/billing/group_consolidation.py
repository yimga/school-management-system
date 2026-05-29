"""Organization-level consolidated AR (global governance Phase 4C)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from apps.finance.org_fx_rollup import SchoolCurrencyBalance, consolidated_org_balances

if TYPE_CHECKING:
    from apps.governance.models import Organization

ORG_BILLING_MODES = frozenset({"per_school", "consolidated", "hybrid"})
DEFAULT_ORG_BILLING_MODE = "per_school"
ORG_BILLING_SETTINGS_KEY = "billing_mode"


def resolve_org_billing_mode(organization: "Organization | None") -> str:
    """Read ``organization``-scoped billing mode from linked school settings or org metadata."""
    if organization is None:
        return DEFAULT_ORG_BILLING_MODE
    # Prefer any member school with explicit org billing flag in settings JSON.
    from apps.schools.models import School

    # tenant-isolation-allow: group-billing-explicit-organization-school-fk-scope
    for school in School.objects.filter(organization=organization).only("settings"):
        settings_blob = getattr(school, "settings", None) or {}
        if not isinstance(settings_blob, dict):
            continue
        org_billing = settings_blob.get("org_billing")
        if isinstance(org_billing, dict):
            mode = str(org_billing.get(ORG_BILLING_SETTINGS_KEY) or "").strip().lower()
            if mode in ORG_BILLING_MODES:
                return mode
    return DEFAULT_ORG_BILLING_MODE


@dataclass(frozen=True)
class ConsolidatedARReport:
    billing_mode: str
    organization_id: str
    balances: tuple[SchoolCurrencyBalance, ...]
    total_open_invoices: int
    currency_exposure: dict[str, Decimal]

    def to_dict(self) -> dict[str, Any]:
        exposure = {code: str(amount) for code, amount in self.currency_exposure.items()}
        return {
            "billing_mode": self.billing_mode,
            "organization_id": self.organization_id,
            "balances": [
                {
                    "school_id": row.school_id,
                    "school_name": row.school_name,
                    "currency_code": row.currency_code,
                    "open_balance": str(row.open_balance),
                    "open_invoice_count": row.open_invoice_count,
                }
                for row in self.balances
            ],
            "total_open_invoices": self.total_open_invoices,
            "currency_exposure": exposure,
        }


def build_consolidated_ar_report(organization: "Organization") -> ConsolidatedARReport:
    """
    Roll up open AR across organization member schools.

  Honors ``billing_mode``: consolidated always rolls up; per_school returns
    rows but marks mode; hybrid includes both per-school rows and exposure totals.
    """
    mode = resolve_org_billing_mode(organization)
    balances = tuple(consolidated_org_balances(organization))
    exposure: dict[str, Decimal] = {}
    total_invoices = 0
    for row in balances:
        total_invoices += row.open_invoice_count
        exposure[row.currency_code] = exposure.get(row.currency_code, Decimal("0")) + row.open_balance

    if mode == "per_school":
        # Still return rows for transparency; callers gate consolidated invoicing.
        pass

    return ConsolidatedARReport(
        billing_mode=mode,
        organization_id=str(organization.pk),
        balances=balances,
        total_open_invoices=total_invoices,
        currency_exposure=exposure,
    )
