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

import json
from datetime import datetime, timedelta
from collections import defaultdict, Counter

from django.shortcuts import render
from django.views import View
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.db.models import Count, Q, Avg
from django.utils import timezone
from django.core.cache import cache
from django.conf import settings

from apps.compliance.models_audit import AuditLog, UserActivitySession, AccessLog
from apps.accounts.models import User


def is_admin_or_staff(user):
    """Check if user is admin or staff."""
    return user.is_superuser or user.is_staff or user.role in ['ADMIN', 'LEADERSHIP']


@method_decorator(login_required, name='dispatch')
@method_decorator(user_passes_test(is_admin_or_staff), name='dispatch')
class ComplianceDashboardView(View):
    """
    Main compliance dashboard with metrics and charts.
    """

    def get(self, request):
        cache_ttl = getattr(settings, "COMPLIANCE_DASHBOARD_CACHE_SECONDS", 60)
        cache_key = "compliance:dashboard:v1"
        context = cache.get(cache_key)

        if not context:
            context = {
                'metrics': self._get_metrics(),
                'activity_chart': self._get_activity_chart(),
                'user_activity_heatmap': self._get_user_activity_heatmap(),
                'model_changes': self._get_model_changes(),
                'permission_overview': self._get_permission_overview(),
                'recent_audits': self._get_recent_audits(),
                'security_summary': self._get_security_summary(),
                'integrity_status': self._get_integrity_status(),
                'threat_metrics': self._get_threat_metrics(),
                'blocked_access': self._get_blocked_access(),
            }
            cache.set(cache_key, context, cache_ttl)
        
        # Add incident response config (not cached, always fresh)
        incident_cfg = getattr(settings, "INCIDENT_RESPONSE", {})
        context['playbook_url'] = incident_cfg.get('playbook_url')
        context['oncall_emails'] = incident_cfg.get('oncall_emails', [])

        return render(request, 'compliance/dashboard.html', context)

    def _get_metrics(self):
        """Get key compliance metrics."""
        now = timezone.now()
        week_ago = now - timedelta(days=7)
        month_ago = now - timedelta(days=30)

        total_users = User.objects.count()
        active_users_week = UserActivitySession.objects.filter(
            login_timestamp__gte=week_ago
        ).values('user').distinct().count()

        total_logins = UserActivitySession.objects.filter(
            login_timestamp__gte=month_ago
        ).count()

        total_audits = AuditLog.objects.filter(
            timestamp__gte=month_ago
        ).count()

        failed_accesses = AccessLog.objects.filter(
            timestamp__gte=week_ago,
            status__gte=400
        ).count()

        suspicious_sessions = UserActivitySession.objects.filter(
            is_suspicious=True,
            login_timestamp__gte=week_ago
        ).count()

        return {
            'total_users': total_users,
            'active_week': active_users_week,
            'activity_rate': f"{(active_users_week/total_users*100):.1f}%" if total_users > 0 else "0%",
            'logins_month': total_logins,
            'audits_month': total_audits,
            'failed_accesses': failed_accesses,
            'suspicious_sessions': suspicious_sessions,
        }

    def _get_activity_chart(self):
        """Get audit activity trend for last 30 days."""
        data = []
        labels = []

        for i in range(29, -1, -1):
            date = (timezone.now() - timedelta(days=i)).date()
            count = AuditLog.objects.filter(
                timestamp__date=date
            ).count()
            data.append(count)
            labels.append(date.strftime('%m-%d'))

        return {
            'labels': labels,
            'data': data,
        }

    def _get_user_activity_heatmap(self):
        """
        Generate user activity heatmap: logins/logouts by hour.
        Returns data for heatmap visualization.
        """
        now = timezone.now()
        week_ago = now - timedelta(days=7)

        # Get login times from last week
        sessions = UserActivitySession.objects.filter(
            login_timestamp__gte=week_ago
        ).values_list('login_timestamp')

        # Create hour counter
        hour_counts = Counter()
        for session in sessions:
            hour = session[0].hour if session[0] else 0
            hour_counts[hour] += 1

        # Format for chart
        hours = list(range(24))
        heatmap_data = [hour_counts.get(h, 0) for h in hours]

        return {
            'hours': hours,
            'data': heatmap_data,
            'period': f"Last 7 days (ending {now.strftime('%Y-%m-%d')})",
        }

    def _get_model_changes(self):
        """Get summary of model changes."""
        now = timezone.now()
        week_ago = now - timedelta(days=7)

        model_stats = AuditLog.objects.filter(
            timestamp__gte=week_ago
        ).values('model_name', 'action').annotate(
            count=Count('id')
        ).order_by('-count')[:20]

        # Group by model
        by_model = defaultdict(lambda: {'creates': 0, 'updates': 0, 'deletes': 0, 'total': 0})

        for stat in model_stats:
            model = stat['model_name']
            action = stat['action']
            count = stat['count']

            by_model[model]['total'] += count
            if action == 'CREATE':
                by_model[model]['creates'] = count
            elif action == 'UPDATE':
                by_model[model]['updates'] = count
            elif action == 'DELETE':
                by_model[model]['deletes'] = count

        return dict(sorted(by_model.items(), key=lambda x: x[1]['total'], reverse=True)[:10])

    def _get_permission_overview(self):
        """Get permission and access overview."""
        # Users by role
        by_role = User.objects.values('role').annotate(
            count=Count('id')
        ).order_by('-count')

        # Access by role
        access_by_role = AccessLog.objects.select_related('user').values(
            'user__role'
        ).annotate(
            total=Count('id'),
            successful=Count('id', filter=Q(status='200')),
            failed=Count('id', filter=Q(status__gte=400)),
        )

        # Most accessed resources
        top_resources = AccessLog.objects.values('resource').annotate(
            count=Count('id')
        ).order_by('-count')[:5]

        # Build permission summary
        permission_summary = {
            'users_by_role': list(by_role),
            'access_by_role': list(access_by_role),
            'top_resources': list(top_resources),
        }

        return permission_summary

    def _get_recent_audits(self):
        """Get recent audit log entries."""
        audits = AuditLog.objects.select_related('user').order_by(
            '-timestamp'
        )[:10].values(
            'timestamp', 'user__username', 'action', 'model_name',
            'object_repr', 'sensitivity'
        )

        return list(audits)

    def _get_security_summary(self):
        """Get security-related metrics."""
        now = timezone.now()
        week_ago = now - timedelta(days=7)

        # Failed logins
        failed_logins = AuditLog.objects.filter(
            timestamp__gte=week_ago,
            action='LOGIN',
            sensitivity='MEDIUM'  # Assuming failed logins marked differently
        ).count()

        # Failed accesses
        failed_accesses = AccessLog.objects.filter(
            timestamp__gte=week_ago,
            status__gte=400
        ).count()

        # Suspicious sessions
        suspicious = UserActivitySession.objects.filter(
            is_suspicious=True,
            login_timestamp__gte=week_ago
        ).count()

        # Permission denials
        denials = AuditLog.objects.filter(
            timestamp__gte=week_ago,
            action='ACCESS_DENIED'
        ).count()

        return {
            'failed_accesses': failed_accesses,
            'suspicious_sessions': suspicious,
            'permission_denials': denials,
            'security_score': self._calculate_security_score(
                failed_accesses, suspicious, denials
            ),
        }

    def _get_integrity_status(self):
        """Get data integrity status."""
        # Quick checks for common issues
        issues = []

        # Check for orphaned records
        from apps.people.models import TeacherProfile
        orphaned_teachers = TeacherProfile.objects.filter(user__isnull=True).count()
        if orphaned_teachers > 0:
            issues.append({
                'type': 'ORPHANED_RECORD',
                'description': f"{orphaned_teachers} orphaned teacher profiles",
                'severity': 'HIGH',
            })

        # Check for users without names
        users_no_name = User.objects.filter(
            Q(first_name='') | Q(first_name__isnull=True)
        ).count()
        if users_no_name > 0:
            issues.append({
                'type': 'MISSING_DATA',
                'description': f"{users_no_name} users missing first name",
                'severity': 'LOW',
            })

        integrity_score = max(0, 100 - len(issues) * 10)

        return {
            'score': integrity_score,
            'status': 'Healthy' if integrity_score >= 90 else 'Warning' if integrity_score >= 70 else 'Critical',
            'issues': issues,
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
        findings = detect_threats(window_minutes=1440)  # 24 hours

        # Get mute status
        try:
            config = ThreatDetectionConfig.get_active()
            is_muted = config.is_muted()
            mute_until = config.mute_until
        except Exception:
            is_muted = False
            mute_until = None

        # Group findings by type
        by_type = defaultdict(int)
        for finding in findings:
            by_type[finding['type']] += 1

        return {
            'total_findings': len(findings),
            'brute_force_user': by_type.get('brute_force_user', 0),
            'brute_force_ip': by_type.get('brute_force_ip', 0),
            'after_hours': by_type.get('after_hours', 0),
            'is_muted': is_muted,
            'mute_until': mute_until,
            'last_checked': timezone.now(),
        }

    def _get_blocked_access(self):
        """Get recent blocked IPs and countries (403 responses)."""
        now = timezone.now()
        last_24h = now - timedelta(days=1)

        # Get recent 403 responses
        blocked = AccessLog.objects.filter(
            timestamp__gte=last_24h,
            status=403
        ).select_related('user').order_by('-timestamp')

        # Aggregate by IP
        by_ip = {}
        by_country = {}

        for log in blocked[:100]:  # Limit to recent 100
            ip = log.ip_address
            if ip not in by_ip:
                by_ip[ip] = {
                    'count': 0,
                    'first_seen': log.timestamp,
                    'last_seen': log.timestamp,
                    'user_agent': log.user_agent or 'Unknown',
                }
            by_ip[ip]['count'] += 1
            by_ip[ip]['last_seen'] = max(by_ip[ip]['last_seen'], log.timestamp)

            # Country (if available)
            country = getattr(log, 'country_code', None)
            if country:
                if country not in by_country:
                    by_country[country] = {
                        'count': 0,
                        'first_seen': log.timestamp,
                    }
                by_country[country]['count'] += 1

        # Sort by count, take top 10
        top_ips = sorted(by_ip.items(), key=lambda x: x[1]['count'], reverse=True)[:10]
        top_countries = sorted(by_country.items(), key=lambda x: x[1]['count'], reverse=True)[:10]

        return {
            'total_blocked': blocked.count(),
            'unique_ips': len(by_ip),
            'top_ips': [{'ip': ip, **data} for ip, data in top_ips],
            'top_countries': [{'code': code, **data} for code, data in top_countries],
        }
