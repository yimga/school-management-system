"""
Global Powerhouse Phase E: Revenue and waiver metrics.
calculate_monthly_stats fills RevenueSnapshot; run on schedule (e.g. Celery Beat daily).
"""
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.schools.models import School
from .models import Plan, RevenueSnapshot


def _first_of_month(d: date) -> date:
    return d.replace(day=1)


def calculate_monthly_stats(snapshot_date: date | None = None) -> dict:
    """
    For each school (tenant), compute actual_revenue and waived_amount for the given month.
    Creates or updates RevenueSnapshot rows.
    Returns summary: total_actual, total_waived, schools_processed, conflicts.
    """
    if snapshot_date is None:
        snapshot_date = _first_of_month(timezone.now().date())
    else:
        snapshot_date = _first_of_month(snapshot_date)

    total_actual = Decimal("0")
    total_waived = Decimal("0")
    schools_processed = 0

    with transaction.atomic():
        for school in School.objects.filter(is_active=True).select_related("plan", "default_region"):
            actual = Decimal("0")
            waived = Decimal("0")
            billing_model = ""
            country_code = (school.default_region_id or "")[:3] if school.default_region_id else ""
            student_count = getattr(school, "_student_count", None)

            # If school is COMPLIMENTARY or MANUAL_OVERRIDE, compute "potential revenue" as waived
            if school.billing_type in (
                School.BillingType.COMPLIMENTARY,
                School.BillingType.MANUAL_OVERRIDE,
            ):
                plan = school.plan
                if plan:
                    bm = plan.billing_model or ""
                    if bm == "FLAT" and plan.base_price is not None:
                        waived = plan.base_price
                    elif bm == "PER_STUDENT" and plan.price_per_student is not None and student_count is not None:
                        waived = plan.price_per_student * student_count
                    elif bm == "TIERED" and plan.tier_rules and student_count is not None:
                        bands = plan.tier_rules if isinstance(plan.tier_rules, list) else []
                        for band in bands:
                            max_stud = band.get("max")
                            price = band.get("price")
                            if max_stud is not None and price is not None and student_count <= max_stud:
                                waived = Decimal(str(price))
                                break
                    billing_model = plan.billing_model or ""
            else:
                # REGULAR / FREE_TRIAL: actual revenue would come from Stripe or payment records
                # Placeholder: 0 unless we integrate payment data later
                plan = school.plan
                if plan:
                    billing_model = plan.billing_model or ""

            if student_count is None:
                try:
                    from apps.people.models import StudentProfile
                    student_count = StudentProfile.objects.filter(school=school).count()
                except Exception:
                    student_count = 0

            snapshot, _ = RevenueSnapshot.objects.update_or_create(
                school=school,
                snapshot_date=snapshot_date,
                defaults={
                    "actual_revenue": actual,
                    "waived_amount": waived,
                    "billing_model": billing_model,
                    "country_code": country_code,
                    "student_count": student_count,
                },
            )
            total_actual += snapshot.actual_revenue
            total_waived += snapshot.waived_amount
            schools_processed += 1

    return {
        "snapshot_date": snapshot_date.isoformat(),
        "total_actual": float(total_actual),
        "total_waived": float(total_waived),
        "schools_processed": schools_processed,
    }
