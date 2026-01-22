"""
Phase 4: Compliance Reporting Views

Provides endpoints for generating, viewing, and exporting compliance reports:
- Audit trail reports (filtered by date, user, model)
- Data access reports
- Permission summaries
- Integrity check reports
- Anomaly detection reports
"""

import csv
import json
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from decimal import Decimal

from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.views import View
from django.views.generic import ListView, DetailView
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.db.models import Q, Count, Max
from django.utils import timezone
from django.conf import settings
from django.db.models.functions import ExtractHour
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors

from apps.compliance.models_audit import AuditLog, UserActivitySession, AccessLog, ComplianceReport
from apps.accounts.models import User


@method_decorator(login_required, name='dispatch')
class AuditTrailReportView(ListView):
    """
    Display comprehensive audit trail with filtering by date, user, model, action, sensitivity.
    """
    model = AuditLog
    template_name = 'compliance/audit_trail_report.html'
    context_object_name = 'audit_logs'
    paginate_by = 50

    def get_queryset(self):
        """Filter audit logs based on request parameters."""
        queryset = AuditLog.objects.all().select_related('user')

        # Date range filter
        days = self.request.GET.get('days', 30)
        try:
            days = int(days)
            start_date = timezone.now() - timedelta(days=days)
            queryset = queryset.filter(timestamp__gte=start_date)
        except (ValueError, TypeError):
            pass

        # User filter
        user_id = self.request.GET.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        # Model filter
        model_name = self.request.GET.get('model')
        if model_name:
            queryset = queryset.filter(model_name__icontains=model_name)

        # Action filter
        action = self.request.GET.get('action')
        if action:
            queryset = queryset.filter(action=action)

        # Sensitivity filter
        sensitivity = self.request.GET.get('sensitivity')
        if sensitivity:
            queryset = queryset.filter(sensitivity=sensitivity)

        return queryset.order_by('-timestamp')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['users'] = User.objects.all()
        context['actions'] = AuditLog.Action.choices
        context['sensitivities'] = AuditLog.Sensitivity.choices
        context['days'] = self.request.GET.get('days', 30)
        context['selected_user'] = self.request.GET.get('user_id')
        context['selected_action'] = self.request.GET.get('action')
        context['selected_sensitivity'] = self.request.GET.get('sensitivity')
        context['selected_model'] = self.request.GET.get('model')
        return context


@method_decorator(login_required, name='dispatch')
class DataAccessReportView(View):
    """
    Generate data access summary:
    - Who accessed what resources
    - When (time patterns)
    - Success/failure rates
    - Error tracking
    """

    def get(self, request):
        days = int(request.GET.get('days', 30))
        start_date = timezone.now() - timedelta(days=days)

        # Get access logs for period
        access_logs = AccessLog.objects.filter(
            timestamp__gte=start_date
        ).select_related('user')

        # Aggregate data
        total_access = access_logs.count()
        successful = access_logs.filter(status='200').count()
        failed = access_logs.exclude(status='200').count()
        
        # By user
        by_user = access_logs.values('user__username').annotate(
            count=Count('id'),
            avg_response_time=avg_response_time('response_time_ms')
        )

        # By access type
        by_type = access_logs.values('access_type').annotate(count=Count('id'))

        # By resource
        by_resource = access_logs.values('resource').annotate(
            count=Count('id'),
            failures=Count('id', filter=Q(status__gte=400))
        ).order_by('-count')[:20]

        context = {
            'total_access': total_access,
            'successful': successful,
            'failed': failed,
            'success_rate': f"{(successful/total_access*100):.1f}%" if total_access > 0 else "N/A",
            'by_user': list(by_user),
            'by_type': list(by_type),
            'by_resource': list(by_resource),
            'days': days,
        }

        return render(request, 'compliance/data_access_report.html', context)


@method_decorator(login_required, name='dispatch')
class PermissionOverviewView(View):
    """
    Permission overview:
    - Users by role
    - Permissions granted/denied
    - Access patterns by role
    """

    def get(self, request):
        users_by_role = User.objects.values('role').annotate(count=Count('id'))
        
        # Access logs by role
        access_by_role = AccessLog.objects.select_related('user').values(
            'user__role'
        ).annotate(
            total_access=Count('id'),
            failed=Count('id', filter=Q(status__gte=400))
        )

        # Most accessed resources
        top_resources = AccessLog.objects.values('resource').annotate(
            access_count=Count('id')
        ).order_by('-access_count')[:10]

        # Most denied resources (4xx errors)
        denied_resources = AccessLog.objects.filter(
            status__gte=400
        ).values('resource').annotate(
            denial_count=Count('id')
        ).order_by('-denial_count')[:10]

        context = {
            'users_by_role': list(users_by_role),
            'access_by_role': list(access_by_role),
            'top_resources': list(top_resources),
            'denied_resources': list(denied_resources),
        }

        return render(request, 'compliance/permission_overview.html', context)


@method_decorator(login_required, name='dispatch')
class IntegrityCheckReportView(View):
    """
    Data integrity check report:
    - Database constraints verification
    - Orphaned references
    - Missing required fields
    - Consistency checks
    """

    def get(self, request):
        issues = []

        # Check for users with no audit logs
        users_without_audit = User.objects.exclude(
            id__in=AuditLog.objects.values_list('user_id', flat=True)
        ).exclude(is_superuser=True)

        if users_without_audit.exists():
            issues.append({
                'type': 'MISSING_AUDIT',
                'description': f"{users_without_audit.count()} users have no audit logs",
                'severity': 'MEDIUM',
                'count': users_without_audit.count()
            })

        # Check for orphaned sessions
        orphaned_sessions = UserActivitySession.objects.filter(
            user__isnull=True
        ).count()

        if orphaned_sessions > 0:
            issues.append({
                'type': 'ORPHANED_SESSIONS',
                'description': f"{orphaned_sessions} orphaned session records",
                'severity': 'HIGH',
                'count': orphaned_sessions
            })

        # Check for access logs with missing models
        access_no_model = AccessLog.objects.filter(
            user__isnull=True
        ).count()

        if access_no_model > 0:
            issues.append({
                'type': 'UNAUTHENTICATED_ACCESS',
                'description': f"{access_no_model} access logs from unauthenticated users",
                'severity': 'MEDIUM',
                'count': access_no_model
            })

        # Check suspicious activity
        suspicious = UserActivitySession.objects.filter(is_suspicious=True).count()
        if suspicious > 0:
            issues.append({
                'type': 'SUSPICIOUS_ACTIVITY',
                'description': f"{suspicious} sessions flagged as suspicious",
                'severity': 'HIGH',
                'count': suspicious
            })

        context = {
            'issues': issues,
            'total_issues': len(issues),
            'critical_count': sum(1 for i in issues if i['severity'] == 'CRITICAL'),
            'high_count': sum(1 for i in issues if i['severity'] == 'HIGH'),
        }

        return render(request, 'compliance/integrity_check_report.html', context)


@method_decorator(login_required, name='dispatch')
class AnomalyDetectionView(View):
    """
    Anomaly detection report:
    - Unusual access patterns
    - Suspicious user activity
    - Peak usage times
    - Error rate anomalies
    """

    def get(self, request):
        days = int(request.GET.get('days', 7))
        start_date = timezone.now() - timedelta(days=days)

        anomalies = []

        # Find users with unusual number of failed accesses
        access_logs = AccessLog.objects.filter(timestamp__gte=start_date)
        
        users_failed = access_logs.filter(
            status__gte=400
        ).values('user__username').annotate(
            failures=Count('id')
        ).filter(failures__gte=10)

        for entry in users_failed:
            username = entry['user__username'] or 'Unknown'
            anomalies.append({
                'type': 'HIGH_FAILURE_RATE',
                'user': username,
                'value': entry['failures'],
                'description': f"User had {entry['failures']} failed access attempts",
                'severity': 'HIGH',
            })

        # Find unusual access times (outside business hours: 6am-10pm)
        unusual_hours = (
            access_logs
            .annotate(hour=ExtractHour('timestamp'))
            .exclude(hour__in=range(6, 22))
            .values('user__username')
            .annotate(count=Count('id'))
            .filter(count__gte=5)
        )

        for entry in unusual_hours:
            username = entry['user__username'] or 'Unknown'
            anomalies.append({
                'type': 'UNUSUAL_ACCESS_TIME',
                'user': username,
                'value': entry['count'],
                'description': f"User accessed system {entry['count']} times outside business hours",
                'severity': 'MEDIUM',
            })

        # Find suspicious sessions
        suspicious_sessions = (
            UserActivitySession.objects.filter(
                login_timestamp__gte=start_date,
                is_suspicious=True
            )
            .select_related('user')
            .only('page_views', 'api_calls', 'notes', 'user__username')
            [:10]
        )

        for session in suspicious_sessions:
            anomalies.append({
                'type': 'SUSPICIOUS_SESSION',
                'user': session.user.username if session.user else 'Unknown',
                'value': session.page_views + session.api_calls,
                'description': f"Session marked as suspicious: {session.notes or 'No details'}",
                'severity': 'HIGH',
            })

        context = {
            'anomalies': anomalies,
            'total_anomalies': len(anomalies),
            'days': days,
        }

        return render(request, 'compliance/anomaly_detection.html', context)


@method_decorator(login_required, name='dispatch')
class ExportComplianceReportView(View):
    """
    Export compliance report in multiple formats (JSON, CSV, PDF).
    """

    def get(self, request):
        report_type = request.GET.get('type', 'audit_trail')
        export_format = request.GET.get('format', 'json')
        days = int(request.GET.get('days', 30))

        start_date = timezone.now() - timedelta(days=days)

        if export_format == 'json':
            return self._export_json(report_type, start_date)
        elif export_format == 'csv':
            return self._export_csv(report_type, start_date)
        elif export_format == 'pdf':
            return self._export_pdf(report_type, start_date)
        else:
            return JsonResponse({'error': 'Invalid format'}, status=400)

    def _export_json(self, report_type, start_date):
        """Export report as JSON."""
        max_rows = getattr(settings, "COMPLIANCE_EXPORT_MAX_ROWS", 5000)
        if report_type == 'audit_trail':
            logs = AuditLog.objects.filter(
                timestamp__gte=start_date
            ).values(
                'timestamp', 'user__username', 'action', 'model_name',
                'object_id', 'sensitivity'
            ).order_by('-timestamp')[:max_rows]
            data = list(logs)
        elif report_type == 'access_log':
            logs = AccessLog.objects.filter(
                timestamp__gte=start_date
            ).values(
                'timestamp', 'user__username', 'resource',
                'request_method', 'status', 'response_time_ms'
            ).order_by('-timestamp')[:max_rows]
            data = list(logs)
        else:
            return JsonResponse({'error': 'Invalid report type'}, status=400)

        response = HttpResponse(
            json.dumps(data, default=str, indent=2),
            content_type='application/json'
        )
        response['Content-Disposition'] = f'attachment; filename="compliance_report_{report_type}.json"'
        return response

    def _export_csv(self, report_type, start_date):
        """Export report as CSV."""
        output = StringIO()
        writer = csv.writer(output)
        max_rows = getattr(settings, "COMPLIANCE_EXPORT_MAX_ROWS", 5000)

        if report_type == 'audit_trail':
            writer.writerow([
                'Timestamp', 'User', 'Action', 'Model', 'Object ID', 'Sensitivity'
            ])
            logs = AuditLog.objects.filter(
                timestamp__gte=start_date
            ).values_list(
                'timestamp', 'user__username', 'action', 'model_name',
                'object_id', 'sensitivity'
            ).order_by('-timestamp')[:max_rows]
            writer.writerows(logs)
        elif report_type == 'access_log':
            writer.writerow([
                'Timestamp', 'User', 'Resource', 'Method', 'Status', 'Response Time (ms)'
            ])
            logs = AccessLog.objects.filter(
                timestamp__gte=start_date
            ).values_list(
                'timestamp', 'user__username', 'resource',
                'request_method', 'status', 'response_time_ms'
            ).order_by('-timestamp')[:max_rows]
            writer.writerows(logs)
        else:
            return JsonResponse({'error': 'Invalid report type'}, status=400)

        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="compliance_report_{report_type}.csv"'
        return response

    def _export_pdf(self, report_type, start_date):
        """Export report as PDF."""
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#1f4788'),
            spaceAfter=12,
        )

        title = Paragraph(f"Compliance Report: {report_type.replace('_', ' ').title()}", title_style)
        elements.append(title)
        elements.append(Spacer(1, 0.3 * inch))

        # Report info
        info_text = f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}<br/>Period: Last 30 days"
        elements.append(Paragraph(info_text, styles['Normal']))
        elements.append(Spacer(1, 0.2 * inch))

        # Data table
        if report_type == 'audit_trail':
            logs = AuditLog.objects.filter(
                timestamp__gte=start_date
            ).values_list(
                'timestamp', 'user__username', 'action', 'model_name', 'sensitivity'
            )[:100]

            data = [['Timestamp', 'User', 'Action', 'Model', 'Sensitivity']]
            for log in logs:
                data.append([
                    log[0].strftime('%Y-%m-%d %H:%M'),
                    log[1] or 'System',
                    log[2],
                    log[3],
                    log[4]
                ])

            table = Table(data, colWidths=[1.5*inch, 1*inch, 1*inch, 1*inch, 1*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f4788')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            elements.append(table)

        doc.build(elements)
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="compliance_report_{report_type}.pdf"'
        return response


def avg_response_time(field_name):
    """Helper to calculate average response time."""
    from django.db.models import Avg
    return Avg(field_name)
