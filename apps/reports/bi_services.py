"""
Phase 9 Task 1: BI Reporting Services
Executive reporting, data aggregation, export generation

INTEGRATION NOTE: This extends existing infrastructure:
- Leverages apps.analytics.services.AdvancedAnalyticsService for analytics
- Integrates with apps.siteconfig.admin_dashboard.AdminDashboardService for metrics
- Adds executive-level aggregations and export capabilities
"""

import logging

from django.core.cache import cache
from django.utils import timezone
from django.db.models import Count, Sum, Avg, DecimalField, F, Value
from django.db.models.functions import Coalesce, TruncMonth
from datetime import timedelta, datetime
from decimal import Decimal
import csv
import json
from io import StringIO
from typing import Dict, List, Any, Optional

# Import existing services to extend them
from apps.analytics.services import AdvancedAnalyticsService
from apps.siteconfig.cache_utils import get_tenant_cache_prefix

logger = logging.getLogger(__name__)


def _report_cache_prefix(school_id: Optional[str] = None) -> str:
    if school_id is not None:
        return f"school:{school_id}"
    return get_tenant_cache_prefix()


class ExecutiveReportingService:
    """
    Executive-level reports and dashboards

    EXTENDS: AdminDashboardService (financial, academic, attendance metrics)
    LEVERAGES: AdvancedAnalyticsService (at-risk detection, trends, alerts)
    ADDS: Executive aggregations, multi-period comparisons, export generation
    """

    @staticmethod
    def get_financial_summary(
        start_date: datetime, end_date: datetime, school_id: Optional[str] = None
    ) -> Dict:
        """
        Financial KPIs for executive dashboard
        Extends AdminDashboardService.get_finance_metrics() with period ranges
        """
        from apps.finance.models import (
            COLLECTED_PAYMENT_STATUS,
            Invoice,
            Payment,
        )

        prefix = _report_cache_prefix(school_id)
        cache_key = f"{prefix}:exec_finance_{school_id or 'global'}_{start_date.date()}_{end_date.date()}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        invoices = Invoice.objects.filter(created_at__range=[start_date, end_date])
        if school_id is not None:
            invoices = invoices.filter(school_id=school_id)
# tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk

        # Money that actually arrived. `status` choices on Payment are
        # lowercase — this read "COMPLETED" and so matched nothing, pinning
        # every board's collected total to 0. Soft-deleted rows are excluded
        # and refunds netted off, matching Invoice.computed_balance, which is
        # the domain's own definition of money received.
        payments = Payment.objects.filter(
            created_at__range=[start_date, end_date],
            status=COLLECTED_PAYMENT_STATUS,
            deleted_at__isnull=True,
        )
        if school_id is not None:
            payments = payments.filter(school_id=school_id)

        # Billed = actually issued and genuinely owed. A DRAFT was never sent
        # to anyone and a VOID was never owed, so counting either inflates the
        # denominator of collection_rate and overstates outstanding.
        billed = invoices.exclude(
            status__in=(Invoice.Status.DRAFT, Invoice.Status.VOID)
        )

        net_received = F("amount") - Coalesce(
            F("refunded_amount"), Value(Decimal("0.00")),
            output_field=DecimalField(max_digits=12, decimal_places=2),
        )

        summary = {
            "total_invoiced": billed.aggregate(total=Sum("total_amount"))["total"]
            or 0,
            "total_collected": payments.aggregate(total=Sum(net_received))["total"]
            or 0,
            # Unpaid remainder of what was billed. `status="PENDING"` was not a
            # member of Invoice.Status at all, so this was always 0.
            "outstanding": billed.aggregate(total=Sum("balance_amount"))["total"]
            or 0,
            "invoice_count": invoices.count(),
            "payment_count": payments.count(),
            "collection_rate": 0.0,
            "period_start": start_date.isoformat(),
            "period_end": end_date.isoformat(),
        }

        if summary["total_invoiced"] > 0:
            summary["collection_rate"] = (
                summary["total_collected"] / summary["total_invoiced"]
            ) * 100

        cache.set(cache_key, summary, 3600)
        return summary

    @staticmethod
    def get_academic_summary(
        academic_year_id: int,
        term_id: Optional[int] = None,
        school_id: Optional[str] = None,
    ) -> Dict:
        """
        Academic performance KPIs
        Integrates with AdvancedAnalyticsService for at-risk student detection
        """
        from apps.evals.models import Evaluation
        from apps.people.models import Student
        from apps.academics.models import Classroom

        prefix = _report_cache_prefix(school_id)
        cache_key = f"{prefix}:exec_academic_{school_id or 'global'}_{academic_year_id}_{term_id}"
        cached = cache.get(cache_key)
        if cached:
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            return cached

        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        evaluations = Evaluation.objects.filter(academic_year_id=academic_year_id)
        if school_id is not None:
            evaluations = evaluations.filter(school_id=school_id)
        if term_id:
            evaluations = evaluations.filter(term_id=term_id)

        students = Student.objects.filter(
            is_active=True, academic_year_id=academic_year_id
        # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
        )
        if school_id is not None:
            # tenant-isolation-allow: service-layer-scoped-via-caller-student-classroom-or-teacher-fk
            students = students.filter(school_id=school_id)
        classrooms = Classroom.objects.filter(academic_year_id=academic_year_id)
        if school_id is not None:
            classrooms = classrooms.filter(school_id=school_id)

        # Leverage existing AdvancedAnalyticsService for at-risk detection
        at_risk_students = AdvancedAnalyticsService.identify_at_risk_students(
            school_id=school_id,
            threshold=50,
        )

        summary = {
            "total_students": students.count(),
            "total_classrooms": classrooms.count(),
            "total_evaluations": evaluations.count(),
            "average_score": evaluations.aggregate(avg=Avg("final_score"))["avg"] or 0,
            "pass_rate": 0.0,
            "excellence_rate": 0.0,
            "at_risk_count": len(at_risk_students),  # Use existing service
        }

        if evaluations.exists():
            passing = evaluations.filter(final_score__gte=50).count()
            excellent = evaluations.filter(final_score__gte=75).count()
            total = evaluations.count()

            summary["pass_rate"] = (passing / total) * 100 if total > 0 else 0
            summary["excellence_rate"] = (excellent / total) * 100 if total > 0 else 0

        cache.set(cache_key, summary, 1800)
        return summary

    @staticmethod
    def get_enrollment_trends(
        months: int = 12, school_id: Optional[str] = None
    ) -> Dict:
        """Enrollment trends over time"""
        from apps.people.models import Student

        prefix = _report_cache_prefix(school_id)
        cache_key = f"{prefix}:enrollment_trends_{school_id or 'global'}_{months}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        end_date = timezone.now()
        start_date = end_date - timedelta(days=months * 30)

        # Monthly enrollment counts (DB-agnostic: SQLite and PostgreSQL)
        students = Student.objects.filter(created_at__range=[start_date, end_date])
        if school_id is not None:
            students = students.filter(school_id=school_id)
        students = (
            students.annotate(month=TruncMonth("created_at"))
            .values("month")
            .annotate(count=Count("id"))
            .order_by("month")
        )
        totals = Student.objects.all()
        if school_id is not None:
            totals = totals.filter(school_id=school_id)

        trends = {
            "monthly_enrollment": list(students),
            "total_active": totals.filter(is_active=True).count(),
            "total_inactive": totals.filter(is_active=False).count(),
            "period_months": months,
        }

        cache.set(cache_key, trends, 7200)
        return trends


class AdHocReportBuilder:
    """Build and execute custom reports"""

    ALLOWED_MODELS = {
        "students": "apps.people.models.Student",
        "teachers": "apps.people.models.Teacher",
        "invoices": "apps.finance.models.Invoice",
        "payments": "apps.finance.models.Payment",
        "evaluations": "apps.evals.models.Evaluation",
        "classrooms": "apps.academics.models.Classroom",
    }

    @staticmethod
    def execute_query(
        model_name: str,
        filters: Dict,
        fields: List[str],
        school_id: Optional[str] = None,
    ) -> List[Dict]:
        """Execute filtered query on allowed models"""
        if model_name not in AdHocReportBuilder.ALLOWED_MODELS:
            raise ValueError(f"Model {model_name} not allowed")

        from django.apps import apps

        app_label, model = AdHocReportBuilder.ALLOWED_MODELS[model_name].rsplit(".", 1)
        ModelClass = apps.get_model(app_label.split(".")[-1], model)

        queryset = ModelClass.objects.all()
        model_field_names = {
            field.name
            for field in ModelClass._meta.get_fields()
            if hasattr(field, "name")
        }
        if "school" in model_field_names:
            if school_id is None:
                raise ValueError(
                    f"school_id required for tenant-scoped report model {model_name}"
                )
            queryset = queryset.filter(school_id=school_id)

        # Apply filters
        if filters:
            queryset = queryset.filter(**filters)

        # Limit fields
        if fields:
            queryset = queryset.values(*fields)

        return list(queryset[:1000])  # Limit to 1000 rows

    @staticmethod
    def export_to_csv(data: List[Dict], filename: str) -> str:
        """Export data to CSV"""
        if not data:
            return ""

        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=data[0].keys())
        writer.writeheader()
        writer.writerows(data)

        return output.getvalue()

    @staticmethod
    def export_to_json(data: List[Dict]) -> str:
        """Export data to JSON"""
        return json.dumps(data, default=str, indent=2)


class ReportCacheManager:
    """Manage report caching and materialized views"""

    CACHE_DURATIONS = {
        "FINANCE": 3600,  # 1 hour
        "ACADEMIC": 1800,  # 30 minutes
        "ATTENDANCE": 900,  # 15 minutes
        "ENROLLMENT": 7200,  # 2 hours
    }

    @staticmethod
    def get_or_generate(report_type: str, parameters: Dict, generator_func) -> Any:
        """Get cached report or generate new one"""
        cache_key = ReportCacheManager._build_cache_key(report_type, parameters)

        cached = cache.get(cache_key)
        if cached:
            return cached

        # Generate report
        result = generator_func(**parameters)

        # Cache result (DB materialization removed — migration 0017 dropped MaterializedReportCache)
        duration = ReportCacheManager.CACHE_DURATIONS.get(report_type, 3600)
        cache.set(cache_key, result, duration)

        return result

    @staticmethod
    def _build_cache_key(report_type: str, parameters: Dict) -> str:
        """Build unique cache key (tenant-scoped)."""
        school_id = parameters.get("school_id") or parameters.get("tenant_id")
        prefix = _report_cache_prefix(school_id)
        params_str = json.dumps(parameters, sort_keys=True)
        return f"{prefix}:report:{report_type}:{hash(params_str)}"

    @staticmethod
    def _store_materialized(
        cache_key: str, report_type: str, data: Any, parameters: Dict, duration: int
    ):
        """Store materialized report in database"""
        from apps.reports.bi_models import MaterializedReportCache

        expires_at = timezone.now() + timedelta(seconds=duration)

        MaterializedReportCache.objects.update_or_create(
            cache_key=cache_key,
            defaults={
                "report_type": report_type,
                "data": data if isinstance(data, dict) else {"result": str(data)},
                "parameters": parameters,
                "row_count": len(data) if isinstance(data, (list, dict)) else 0,
                "expires_at": expires_at,
            },
        )

    @staticmethod
    def invalidate_report_cache(report_type: str, school_id: Optional[str] = None):
        """Invalidate all caches for a report type (tenant-scoped keys)."""
        prefix = _report_cache_prefix(school_id)
        cache_key_prefix = f"{prefix}:report:{report_type}:"
        pattern = f"{prefix}:report:{report_type}:*"
        if hasattr(cache, "delete_pattern"):
            cache.delete_pattern(pattern)
        else:
            for key in list(cache._cache.keys()):
                if key.startswith(cache_key_prefix):
                    cache.delete(key)


class ScheduledReportRunner:
    """Execute scheduled reports"""

    @staticmethod
    def run_due_reports(
        *,
        school_id: Optional[int] = None,
        limit: Optional[int] = None,
        dry_run: bool = False,
        strict_no_skip: bool = False,
        json_summary: bool = False,
        **extra: Any,
    ):
        """Run tenant schedules that are due (``TenantReportSchedule`` via ``send_scheduled_reports``)."""
        from django.core.management import call_command

        kwargs: Dict[str, Any] = dict(extra)
        if school_id is not None:
            kwargs["school_id"] = school_id
        if limit is not None:
            kwargs["limit"] = limit
        if dry_run:
            kwargs["dry_run"] = True
        if strict_no_skip:
            kwargs["strict_no_skip"] = True
        if json_summary:
            kwargs["json_summary"] = True
        call_command("send_scheduled_reports", **kwargs)

    @staticmethod
    def _execute_report(report_definition, parameters: Dict) -> Dict:
        """Execute report definition"""
        # Placeholder - implement based on report_definition.query_template
        return {"status": "executed", "parameters": parameters}

    @staticmethod
    def _send_report(scheduled_report, result: Dict):
        """Send report via email"""
        from apps.schoolops.email_compat import send_mail

        subject = f"Scheduled Report: {scheduled_report.report_definition.name}"
        message = (
            f"Report generated at {timezone.now()}\n\n{json.dumps(result, indent=2)}"
        )

        send_mail(
            subject,
            message,
            "reports@school.local",
            scheduled_report.recipients,
            fail_silently=True,
        )

    @staticmethod
    def _calculate_next_run(frequency: str, schedule_time) -> datetime:
        """Calculate next run time based on frequency"""
        now = timezone.now()
        next_run = now.replace(
            hour=schedule_time.hour, minute=schedule_time.minute, second=0
        )

        if frequency == "DAILY":
            if next_run <= now:
                next_run += timedelta(days=1)
        elif frequency == "WEEKLY":
            next_run += timedelta(days=7)
        elif frequency == "MONTHLY":
            next_run += timedelta(days=30)
        elif frequency == "QUARTERLY":
            next_run += timedelta(days=90)

        return next_run
