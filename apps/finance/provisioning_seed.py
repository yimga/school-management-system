"""Per-tenant finance defaults seeded during provisioning Phase B.

``apps.finance`` is a TENANT_APPS app (schema-per-tenant), so a freshly provisioned
tenant schema starts with **zero** ``ComplianceProfile`` rows. ``Invoice.profile`` is a
``PROTECT``, non-null FK, and fee/invoice creation resolves the profile via
``site.compliance_profile`` → fallback ``ComplianceProfile.objects.filter(is_active=True).first()``
*inside the tenant schema*. The platform ``RuntimeDefaults.compliance_profile_id`` points at a
row in the public schema whose pk does not exist in the tenant schema, so that path returns
``None`` and the fallback runs against an empty table → ``None`` → ``IntegrityError`` the moment a
school generates fees.

This module guarantees at least one active, region-aware ``ComplianceProfile`` exists *in the
tenant schema*, so the fallback always resolves. It deliberately does **not** write to the shared
``RuntimeDefaults`` (the ``compliance_profile`` setter targets public-schema pk=1; setting it from a
tenant context would clobber the global default with a tenant-local pk).

Idempotent: safe to re-run on provisioning retry / stuck-tenant recovery, and never overwrites an
operator's existing profile.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


def _resolve_country_code(school: Any) -> str:
    code = (getattr(school, "country_code", "") or "").strip().upper()
    return code[:2] if code else "WW"


def _resolve_currency(school: Any) -> str:
    """Best-effort 3-letter currency. Provisioning merges ``profile.default_currency``
    into ``school.settings``; fall back to USD when absent/malformed."""
    settings_blob = getattr(school, "settings", None) or {}
    if isinstance(settings_blob, dict):
        cur = settings_blob.get("default_currency")
        if isinstance(cur, str) and len(cur.strip()) == 3:
            return cur.strip().upper()
    return "USD"


def ensure_tenant_compliance_profile(school: Any) -> Any | None:
    """Ensure the current tenant schema has at least one active ``ComplianceProfile``.

    Returns the resolved/created profile, or ``None`` on soft failure. Idempotent: if an active
    profile already exists it is returned unchanged (operator edits are never overwritten).

    MUST be called inside the tenant schema context (e.g. provisioning Phase B's
    ``_optional_tenant_context``), so the row lands in the right schema.
    """
    from apps.finance.models import ComplianceProfile

    existing = (
        ComplianceProfile.objects.filter(is_active=True).order_by("pk").first()
    )
    if existing is not None:
        return existing

    country_code = _resolve_country_code(school)
    currency = _resolve_currency(school)
    name = f"{(getattr(school, 'name', None) or 'School')} Default"

    profile, _created = ComplianceProfile.objects.get_or_create(
        name=name,
        country_code=country_code,
        defaults={
            "currency_code": currency,
            "currency_symbol": currency,
            "chart_template": ComplianceProfile.ChartTemplate.GENERIC,
            "min_wage": Decimal("0"),
            "default_hours_per_week": Decimal("0"),
            "overtime_multiplier": Decimal("1.5"),
            "annual_leave_days": 0,
            "maternity_leave_days": 0,
            "is_active": True,
        },
    )
    return profile


def ensure_tenant_default_fee_plan(school: Any, *, academic_year: Any = None) -> Any | None:
    """Ensure a freshly provisioned tenant has at least one editable ``FeePlan``.

    A brand-new tenant schema starts with **zero** fee plans, so the Fees surface renders
    blank and ``auto_generate_fee_invoices_task`` dead-ends on ``{"status": "no_plans"}`` — the
    school literally cannot invoice on day one (the lived-experience gap-doc's P0 item). This
    seeds a single **zero-amount** starter plan carrying one editable ``TUITION`` item that the
    school edits or duplicates per class. **No money is charged until the school sets an amount.**

    Idempotent and non-destructive:
      * If the year already has ANY fee plan (the operator has started), it returns without
        touching anything — an operator's plans are never joined by a stray default.
      * Otherwise it creates the starter via ``get_or_create``, so a provisioning retry / the
        half-provisioned reconcile sweep never duplicates it.

    Tenant safety: every read is a reverse-relation accessor off the passed-in, school-scoped
    ``academic_year`` (``.fee_plans`` / ``.classrooms``) or an ``order_by`` — no unscoped
    ``Model.objects`` query is issued, so this stays inside tenant isolation by construction.

    MUST be called inside the tenant schema context (provisioning Phase B) and given the
    school's active ``AcademicYear`` (the row Phase B just seeded). Returns the plan, or
    ``None`` when it declines/cannot seed (no year / no classroom / no specialty yet).
    """
    if academic_year is None:
        return None

    from apps.academics.models import Specialty
    from apps.finance.models import FeeItem, FeePlan

    if academic_year.fee_plans.exists():
        return None  # school already has plans; never add a default alongside them

    classroom = academic_year.classrooms.order_by("name").first()
    specialty = Specialty.objects.order_by("pk").first()
    if classroom is None or specialty is None:
        # Academic skeleton not fully seeded yet (mid-provision). A Phase-B retry
        # (reconcile_half_provisioned_tenants) will re-run this once it exists.
        return None

    plan, created = FeePlan.objects.get_or_create(
        academic_year=academic_year,
        classroom=classroom,
        specialty=specialty,
        name="Default Tuition Plan",
        defaults={
            "school": school if getattr(school, "pk", None) else None,
            "is_active": True,
            "notes": (
                "Starter plan created during setup. Edit the tuition amount below "
                "(or duplicate this plan for each class) to begin invoicing. No fees "
                "are charged until you set an amount."
            ),
        },
    )
    if created:
        FeeItem.objects.create(
            plan=plan,
            name="Tuition (set your amount)",
            amount=Decimal("0"),
            item_type=FeeItem.ItemType.TUITION,
            is_mandatory=True,
        )
    return plan
