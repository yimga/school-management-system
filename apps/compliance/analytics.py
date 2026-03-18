"""Compliance analytics and reporting for Phase 1.2.9"""

from django.db.models import Avg
from django.utils import timezone
from datetime import timedelta
from apps.compliance.models import (
    ComplianceCheck,
    RegionalComplianceRequirement,
    ComplianceAuditLog,
    LegalDocument,
)
from apps.global_registries.models import RegionConfig


class ComplianceAnalytics:
    """Analytics engine for compliance metrics and reporting."""

    def __init__(self):
        self.timestamp = timezone.now()

    def get_compliance_overview(self):
        """Get overall compliance metrics across all regions."""
        total_regions = RegionConfig.objects.count()
        total_requirements = RegionalComplianceRequirement.objects.count()
        completed = RegionalComplianceRequirement.objects.filter(
            status__in=["implemented", "active"]
        ).count()
        pending = RegionalComplianceRequirement.objects.filter(status="pending").count()
        overdue = sum(
            1 for r in RegionalComplianceRequirement.objects.all() if r.is_overdue()
        )

        return {
            "total_regions": total_regions,
            "total_requirements": total_requirements,
            "completed": completed,
            "pending": pending,
            "overdue": overdue,
            "completion_percentage": round(
                (completed / total_requirements * 100) if total_requirements > 0 else 0,
                1,
            ),
            "on_time_percentage": round(
                ((total_requirements - overdue) / total_requirements * 100)
                if total_requirements > 0
                else 0,
                1,
            ),
        }

    def get_regional_metrics(self):
        """Get compliance metrics per region."""
        metrics = {}
        for region in RegionConfig.objects.all():
            reqs = RegionalComplianceRequirement.objects.filter(region=region)
            active = reqs.filter(status__in=["implemented", "active"]).count()
            total = reqs.count()
            overdue = sum(1 for r in reqs if r.is_overdue())

            metrics[region.code] = {
                "region_name": region.name,
                "total_requirements": total,
                "completed": active,
                "pending": total - active,
                "overdue": overdue,
                "compliance_score": round(
                    (active / total * 100) if total > 0 else 0, 1
                ),
                "status": "Critical"
                if overdue > 0
                else ("On Track" if active == total else "At Risk"),
            }

        return metrics

    def get_check_statistics(self):
        """Get compliance check statistics."""
        checks = ComplianceCheck.objects.all()
        total_checks = checks.count()

        passed = checks.filter(status="pass").count()
        failed = checks.filter(status="fail").count()
        warnings = checks.filter(status="warning").count()

        avg_issues = checks.aggregate(Avg("issues_found"))["issues_found__avg"] or 0

        return {
            "total_checks": total_checks,
            "passed": passed,
            "failed": failed,
            "warnings": warnings,
            "pass_rate": round(
                (passed / total_checks * 100) if total_checks > 0 else 0, 1
            ),
            "fail_rate": round(
                (failed / total_checks * 100) if total_checks > 0 else 0, 1
            ),
            "average_issues_per_check": round(avg_issues, 2),
        }

    def get_audit_log_summary(self, days=30):
        """Get audit log summary for last N days."""
        date_threshold = timezone.now() - timedelta(days=days)
        logs = ComplianceAuditLog.objects.filter(timestamp__gte=date_threshold)

        action_counts = {}
        severity_counts = {}

        for log in logs:
            action_counts[log.action_type] = action_counts.get(log.action_type, 0) + 1
            severity_counts[log.severity] = severity_counts.get(log.severity, 0) + 1

        return {
            "period_days": days,
            "total_actions": logs.count(),
            "action_breakdown": action_counts,
            "severity_breakdown": severity_counts,
        }

    def get_document_status(self):
        """Get legal document coverage and status."""
        docs = LegalDocument.objects.filter(is_active=True)

        doc_types = {}
        for doc_type, _ in docs.model._meta.get_field("document_type").choices:
            count = docs.filter(document_type=doc_type).count()
            languages = (
                docs.filter(document_type=doc_type)
                .values("language")
                .distinct()
                .count()
            )
            doc_types[doc_type] = {"count": count, "languages": languages}

        expired = docs.filter(expiry_date__lt=timezone.now().date()).count()

        return {
            "total_active_documents": docs.count(),
            "documents_by_type": doc_types,
            "expired_documents": expired,
            "coverage": f"{docs.count()} documents across {docs.values('language').distinct().count()} languages",
        }

    def get_timeline_data(self, days=90):
        """Get compliance data over time for timeline visualization."""
        timeline = []
        for i in range(days, 0, -1):
            date = (timezone.now() - timedelta(days=i)).date()
            checks_that_day = ComplianceCheck.objects.filter(check_date__date=date)
            logs_that_day = ComplianceAuditLog.objects.filter(timestamp__date=date)

            timeline.append(
                {
                    "date": date.isoformat(),
                    "checks_performed": checks_that_day.count(),
                    "pass_rate": round(
                        (
                            checks_that_day.filter(status="pass").count()
                            / checks_that_day.count()
                            * 100
                        )
                        if checks_that_day.count() > 0
                        else 0,
                        1,
                    ),
                    "audit_actions": logs_that_day.count(),
                }
            )

        return timeline

    def get_regional_comparison(self, regions=None):
        """Compare compliance status across regions."""
        if not regions:
            regions = RegionConfig.objects.all()

        comparison = []
        for region in regions:
            reqs = RegionalComplianceRequirement.objects.filter(region=region)
            checks = ComplianceCheck.objects.filter(region=region)

            completed = reqs.filter(status__in=["implemented", "active"]).count()
            total_reqs = reqs.count()
            passed_checks = checks.filter(status="pass").count()
            total_checks = checks.count()

            comparison.append(
                {
                    "region_code": region.code,
                    "region_name": region.name,
                    "requirement_completion": round(
                        (completed / total_reqs * 100) if total_reqs > 0 else 0, 1
                    ),
                    "check_pass_rate": round(
                        (passed_checks / total_checks * 100) if total_checks > 0 else 0,
                        1,
                    ),
                    "total_requirements": total_reqs,
                    "total_checks": total_checks,
                    "overdue_count": sum(1 for r in reqs if r.is_overdue()),
                }
            )

        # Sort by requirement completion
        comparison.sort(key=lambda x: x["requirement_completion"], reverse=True)
        return comparison

    def get_critical_items(self):
        """Get critical compliance items requiring attention."""
        critical = []

        # Overdue requirements
        for req in RegionalComplianceRequirement.objects.all():
            if req.is_overdue():
                critical.append(
                    {
                        "type": "overdue_requirement",
                        "region": req.region.code,
                        "description": f"{req.rule.name} - {(timezone.now().date() - req.deadline).days} days overdue",
                        "severity": "critical",
                        "deadline": req.deadline.isoformat(),
                    }
                )

        # Failed compliance checks
        for check in ComplianceCheck.objects.filter(status="fail").order_by(
            "-check_date"
        )[:10]:
            if check.issues_found > 0:
                critical.append(
                    {
                        "type": "failed_check",
                        "region": check.region.code,
                        "description": f"{check.get_check_type_display()} - {check.issues_found} issues",
                        "severity": "high",
                        "date": check.check_date.isoformat(),
                    }
                )

        # Expired documents
        for doc in LegalDocument.objects.filter(expiry_date__lt=timezone.now().date()):
            critical.append(
                {
                    "type": "expired_document",
                    "region": doc.region.code,
                    "description": f"{doc.get_document_type_display()} ({doc.language.upper()}) expired",
                    "severity": "high",
                    "expiry_date": doc.expiry_date.isoformat(),
                }
            )

        return sorted(
            critical,
            key=lambda x: {"critical": 0, "high": 1, "medium": 2}.get(x["severity"], 3),
        )
