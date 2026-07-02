"""
Phase 4: Admin Dashboard & Compliance Metrics

Provides comprehensive compliance dashboard for administrators:
- User activity heatmap (logins/logouts by hour)
- Data change summary (models modified, actions taken)
- Permission overview (users by role, access patterns)
- Audit log statistics (recent activity, trend analysis)
- Data integrity status
- Security summary (failed logins, suspicious activity)
"""

from collections import defaultdict, Counter
from datetime import timedelta
import json

from django.shortcuts import render
from django.views import View
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.db import DatabaseError, IntegrityError, OperationalError
from django.db.models import Count, Q
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings

from apps.compliance.models_audit import AuditLog, UserActivitySession, AccessLog
from apps.compliance.auth_utils import is_admin_or_staff
from apps.compliance.tenant_scope import (
    get_compliance_scope_school,
    school_user_queryset,
    scope_access_logs,
    scope_audit_logs,
    scope_sessions,
)
from apps.platform_runtime.structured_logging import log_exception_with_context

SUCCESS_ACCESS_FILTER = Q(status=AccessLog.Status.SUCCESS) | Q(status="200")
FAILED_ACCESS_FILTER = ~SUCCESS_ACCESS_FILTER
FORBIDDEN_ACCESS_FILTER = Q(status=AccessLog.Status.FORBIDDEN) | Q(status="403")


@method_decorator(login_required, name="dispatch")
@method_decorator(user_passes_test(is_admin_or_staff), name="dispatch")
class ComplianceDashboardView(View):
    """
    Main compliance dashboard with metrics and charts.
    """

    def get(self, request):
        from apps.siteconfig.cache_utils import get_tenant_cache_prefix

        self.scope_school = get_compliance_scope_school(request)
        cache_ttl = getattr(settings, "COMPLIANCE_DASHBOARD_CACHE_SECONDS", 60)
        prefix = get_tenant_cache_prefix(request)
        cache_key = f"{prefix}:compliance:dashboard:v1"
        context = cache.get(cache_key)

        if not context:
            context = {
                "metrics": self._get_metrics(),
                "activity_chart": self._get_activity_chart(),
                "user_activity_heatmap": self._get_user_activity_heatmap(),
                "model_changes": self._get_model_changes(),
                "permission_overview": self._get_permission_overview(),
                "recent_audits": self._get_recent_audits(),
                "security_summary": self._get_security_summary(),
                "integrity_status": self._get_integrity_status(),
                "threat_metrics": self._get_threat_metrics(),
                "blocked_access": self._get_blocked_access(),
            }
            cache.set(cache_key, context, cache_ttl)

        activity_chart = context.get("activity_chart")
        if isinstance(activity_chart, dict):
            activity_chart.setdefault("labels_json", json.dumps(activity_chart.get("labels") or []))
            activity_chart.setdefault("data_json", json.dumps(activity_chart.get("data") or []))
            context["activity_chart_labels_json"] = activity_chart["labels_json"]
            context["activity_chart_data_json"] = activity_chart["data_json"]
        heatmap = context.get("user_activity_heatmap")
        if isinstance(heatmap, dict):
            context["user_activity_heatmap_hours_json"] = json.dumps(heatmap.get("hours") or [])
            context["user_activity_heatmap_data_json"] = json.dumps(heatmap.get("data") or [])

        # Add incident response config (not cached, always fresh)
        incident_cfg = getattr(settings, "INCIDENT_RESPONSE", {})
        context["playbook_url"] = incident_cfg.get("playbook_url")
        context["oncall_emails"] = incident_cfg.get("oncall_emails", [])

        m = context.get("metrics") or {}
        integrity = context.get("integrity_status") or {}
        failed = int(m.get("failed_accesses") or 0)
        suspicious = int(m.get("suspicious_sessions") or 0)
        recent = context.get("recent_audits") or []
        activity_rows = []
        for row in list(recent)[:4]:
            if isinstance(row, dict):
                who = row.get("user__username") or ""
                obj = row.get("object_repr") or ""
                activity_rows.append(
                    {
                        "title": str(row.get("action") or "Audit event"),
                        "meta": " ".join(
                            x for x in (str(who), str(obj)[:80]) if x
                        ).strip()
                        or str(row.get("timestamp") or ""),
                    }
                )
            else:
                activity_rows.append(
                    {"title": str(getattr(row, "action", "Audit")), "meta": ""}
                )
        if not activity_rows:
            activity_rows.append(
                {"title": "Compliance monitoring", "meta": "No recent audit rows."}
            )
        from django.urls import reverse as _reverse

        urgent = []
        if failed > 10:
            urgent.append(
                {
                    "title": f"{failed} failed accesses (week)",
                    "url": "",
                    "hint": "Review access patterns and RBAC.",
                }
            )
        if suspicious:
            urgent.append(
                {
                    "title": f"{suspicious} suspicious session(s)",
                    "url": "",
                    "hint": "Investigate flagged sessions.",
                }
            )
        if not urgent:
            urgent.append(
                {
                    "title": "No critical access spikes",
                    "url": "",
                    "hint": "Continue monitoring audit stream.",
                }
            )

        context["phase7_de"] = {
            "eyebrow": "Compliance home",
            "headline_label": "Integrity score",
            "headline_value": f"{integrity.get('score', 0)}%",
            "headline_meta": str(integrity.get("status", "")),
            "metrics": [
                {
                    "label": "Active users (week)",
                    "value": m.get("active_week", 0),
                    "meta": f"/ {m.get('total_users', 0)} total",
                    "status": "ok",
                },
                {
                    "label": "Failed accesses",
                    "value": failed,
                    "meta": "Past 7 days",
                    "status": "danger" if failed > 10 else "warn" if failed else "ok",
                },
                {
                    "label": "Audit events (month)",
                    "value": m.get("audits_month", 0),
                    "meta": "Recorded",
                    "status": "ok",
                },
            ],
            "urgent_queue": urgent,
            "next_actions": [
                {
                    "label": "Open playbook",
                    "url": context.get("playbook_url") or "#",
                },
                {"label": "Reload dashboard", "url": request.get_full_path()},
                {
                    "label": "Backend home",
                    "url": _reverse("accounts:backend_dashboard"),
                },
            ],
            "activity": activity_rows,
        }

        context.setdefault("activity_chart_labels_json", "[]")
        context.setdefault("activity_chart_data_json", "[]")
        context.setdefault("user_activity_heatmap_hours_json", "[]")
        context.setdefault("user_activity_heatmap_data_json", "[]")
        return render(request, "compliance/dashboard.html", context)

    def _get_metrics(self):
        """Get key compliance metrics."""
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)
        school = getattr(self, "scope_school", None)

        total_users = school_user_queryset(school).count()
        active_users_week = (
            scope_sessions(
                UserActivitySession.objects.filter(login_timestamp__gte=week_ago),
                school,
            )
            .values("user")
            .distinct()
            .count()
        )

        total_logins = scope_sessions(
            UserActivitySession.objects.filter(login_timestamp__gte=month_ago), school
        ).count()

        total_audits = scope_audit_logs(
            AuditLog.objects.filter(timestamp__gte=month_ago), school
        ).count()

        failed_accesses = (
            scope_access_logs(
                AccessLog.objects.filter(
                    timestamp__gte=week_ago,
                ),
                school,
            )
            .filter(FAILED_ACCESS_FILTER)
            .count()
        )

        suspicious_sessions = scope_sessions(
            UserActivitySession.objects.filter(
                is_suspicious=True, login_timestamp__gte=week_ago
            ),
            school,
        ).count()

        return {
            "total_users": total_users,
            "active_week": active_users_week,
            "activity_rate": f"{(active_users_week / total_users * 100):.1f}%"
            if total_users > 0
            else "0%",
            "logins_month": total_logins,
            "audits_month": total_audits,
            "failed_accesses": failed_accesses,
            "suspicious_sessions": suspicious_sessions,
        }

    def _get_activity_chart(self):
        """Get audit activity trend for last 30 days."""
        data = []
        labels = []
        school = getattr(self, "scope_school", None)

        for i in range(29, -1, -1):
            date = (timezone.now() - timedelta(days=i)).date()
            count = scope_audit_logs(
                AuditLog.objects.filter(timestamp__date=date), school
            ).count()
            data.append(count)
            labels.append(date.strftime("%m-%d"))

        return {
            "labels": labels,
            "labels_json": json.dumps(labels),
            "data": data,
            "data_json": json.dumps(data),
        }

    def _get_user_activity_heatmap(self):
        """
        Generate user activity heatmap: logins/logouts by hour.
        Returns data for heatmap visualization.
        """
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        school = getattr(self, "scope_school", None)

        # Get login times from last week
        sessions = scope_sessions(
            UserActivitySession.objects.filter(login_timestamp__gte=week_ago), school
        ).values_list("login_timestamp")

        # Create hour counter
        hour_counts = Counter()
        for session in sessions:
            hour = session[0].hour if session[0] else 0
            hour_counts[hour] += 1

        # Format for chart
        hours = list(range(24))
        heatmap_data = [hour_counts.get(h, 0) for h in hours]

        return {
            "hours": hours,
            "data": heatmap_data,
            "period": f"Last 7 days (ending {now.strftime('%Y-%m-%d')})",
        }

    def _get_model_changes(self):
        """Get summary of model changes."""
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        school = getattr(self, "scope_school", None)

        model_stats = (
            scope_audit_logs(AuditLog.objects.filter(timestamp__gte=week_ago), school)
            .values("model_name", "action")
            .annotate(count=Count("id"))
            .order_by("-count")[:20]
        )

        # Group by model
        by_model = defaultdict(
            lambda: {"creates": 0, "updates": 0, "deletes": 0, "total": 0}
        )

        for stat in model_stats:
            model = stat["model_name"]
            action = stat["action"]
            count = stat["count"]

            by_model[model]["total"] += count
            if action == "CREATE":
                by_model[model]["creates"] = count
            elif action == "UPDATE":
                by_model[model]["updates"] = count
            elif action == "DELETE":
                by_model[model]["deletes"] = count

        return dict(
            sorted(by_model.items(), key=lambda x: x[1]["total"], reverse=True)[:10]
        )

    def _get_permission_overview(self):
        """Get permission and access overview."""
        school = getattr(self, "scope_school", None)
        # Users by role
        by_role = (
            school_user_queryset(school)
            .values("role")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        # Access by role
        access_by_role = (
            scope_access_logs(AccessLog.objects.select_related("user"), school)
            .values("user__role")
            .annotate(
                total=Count("id"),
                successful=Count("id", filter=SUCCESS_ACCESS_FILTER),
                failed=Count("id", filter=FAILED_ACCESS_FILTER),
            )
        )

        # Most accessed resources
        top_resources = (
            scope_access_logs(AccessLog.objects.all(), school)
            .values("resource")
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )

        # Build permission summary
        permission_summary = {
            "users_by_role": list(by_role),
            "access_by_role": list(access_by_role),
            "top_resources": list(top_resources),
        }

        return permission_summary

    def _get_recent_audits(self):
        """Get recent audit log entries."""
        school = getattr(self, "scope_school", None)
        audits = (
            scope_audit_logs(AuditLog.objects.select_related("user"), school)
            .order_by("-timestamp")[:10]
            .values(
                "timestamp",
                "user__username",
                "action",
                "model_name",
                "object_repr",
                "sensitivity",
            )
        )

        return list(audits)

    def _get_security_summary(self):
        """Get security-related metrics."""
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        school = getattr(self, "scope_school", None)

        # Failed logins
        AuditLog.objects.filter(
            timestamp__gte=week_ago,
            action="LOGIN",
            sensitivity="MEDIUM",  # Assuming failed logins marked differently
        ).count()

        # Failed accesses
        failed_accesses = (
            scope_access_logs(
                AccessLog.objects.filter(
                    timestamp__gte=week_ago,
                ),
                school,
            )
            .filter(FAILED_ACCESS_FILTER)
            .count()
        )

        # Suspicious sessions
        suspicious = scope_sessions(
            UserActivitySession.objects.filter(
                is_suspicious=True, login_timestamp__gte=week_ago
            ),
            school,
        ).count()

        # Permission denials
        denials = scope_audit_logs(
            AuditLog.objects.filter(timestamp__gte=week_ago, action="ACCESS_DENIED"),
            school,
        ).count()

        return {
            "failed_accesses": failed_accesses,
            "suspicious_sessions": suspicious,
            "permission_denials": denials,
            "security_score": self._calculate_security_score(
                failed_accesses, suspicious, denials
            ),
        }

    def _get_integrity_status(self):
        """Get data integrity status."""
        # Quick checks for common issues
        issues = []
        school = getattr(self, "scope_school", None)

        # Check for orphaned records
        from apps.people.models import TeacherProfile

        orphaned_teachers = TeacherProfile.objects.filter(
            user__isnull=True, **({"school": school} if school is not None else {})
        ).count()
        if orphaned_teachers > 0:
            issues.append(
                {
                    "type": "ORPHANED_RECORD",
                    "description": f"{orphaned_teachers} orphaned teacher profiles",
                    "severity": "HIGH",
                }
            )

        # Check for users without names
        users_no_name = (
            school_user_queryset(school)
            .filter(Q(first_name="") | Q(first_name__isnull=True))
            .count()
        )
        if users_no_name > 0:
            issues.append(
                {
                    "type": "MISSING_DATA",
                    "description": f"{users_no_name} users missing first name",
                    "severity": "LOW",
                }
            )

        integrity_score = max(0, 100 - len(issues) * 10)

        return {
            "score": integrity_score,
            "status": "Healthy"
            if integrity_score >= 90
            else "Warning"
            if integrity_score >= 70
            else "Critical",
            "issues": issues,
        }

    def _calculate_security_score(self, failed_accesses, suspicious, denials):
        """Calculate overall security score (0-100)."""
        # Start at 100, deduct based on issues
        score = 100
        score -= min(failed_accesses * 0.5, 20)  # Max deduct 20
        score -= min(suspicious * 5, 30)  # Max deduct 30
        score -= min(denials * 1, 20)  # Max deduct 20
        return max(0, score)

    def _get_threat_metrics(self):
        """Get threat detection metrics for last 24 hours."""
        from apps.compliance.threat_detection import detect_threats
        from apps.compliance.models_audit import ThreatDetectionConfig

        # Run detection for last 24 hours
        findings = detect_threats(
            window_minutes=1440, school=getattr(self, "scope_school", None)
        )

        # Get mute status
        try:
            config = ThreatDetectionConfig.get_active()
            is_muted = config.is_muted()
            mute_until = config.mute_until
        except (
            AttributeError,
            TypeError,
            ValueError,
            DatabaseError,
            OperationalError,
            IntegrityError,
        ):
            log_exception_with_context(
                "compliance dashboard threat config lookup failed",
                school_id=getattr(self, "scope_school", None),
                extra={"section": "_get_threat_metrics"},
            )
            is_muted = False
            mute_until = None

        # Group findings by type
        by_type = defaultdict(int)
        for finding in findings:
            by_type[finding["type"]] += 1

        return {
            "total_findings": len(findings),
            "brute_force_user": by_type.get("brute_force_user", 0),
            "brute_force_ip": by_type.get("brute_force_ip", 0),
            "after_hours": by_type.get("after_hours", 0),
            "is_muted": is_muted,
            "mute_until": mute_until,
            "last_checked": timezone.now(),
        }

    def _get_blocked_access(self):
        """Get recent blocked IPs and countries (403 responses)."""
        now = timezone.now()
        last_24h = now - timedelta(days=1)
        school = getattr(self, "scope_school", None)

        # Get recent 403 responses
        blocked = (
            scope_access_logs(
                AccessLog.objects.filter(
                    FORBIDDEN_ACCESS_FILTER,
                    timestamp__gte=last_24h,
                ),
                school,
            )
            .select_related("user")
            .order_by("-timestamp")
        )

        # Aggregate by IP
        by_ip = {}
        by_country = {}

        for log in blocked[:100]:  # Limit to recent 100
            ip = log.ip_address
            if ip not in by_ip:
                by_ip[ip] = {
                    "count": 0,
                    "first_seen": log.timestamp,
                    "last_seen": log.timestamp,
                    "user_agent": log.user_agent or "Unknown",
                }
            by_ip[ip]["count"] += 1
            by_ip[ip]["last_seen"] = max(by_ip[ip]["last_seen"], log.timestamp)

            # Country (if available)
            country = getattr(log, "country_code", None)
            if country:
                if country not in by_country:
                    by_country[country] = {
                        "count": 0,
                        "first_seen": log.timestamp,
                    }
                by_country[country]["count"] += 1

        # Sort by count, take top 10
        top_ips = sorted(by_ip.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
        top_countries = sorted(
            by_country.items(), key=lambda x: x[1]["count"], reverse=True
        )[:10]

        return {
            "total_blocked": blocked.count(),
            "unique_ips": len(by_ip),
            "top_ips": [{"ip": ip, **data} for ip, data in top_ips],
            "top_countries": [{"code": code, **data} for code, data in top_countries],
        }
