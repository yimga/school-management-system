"""
Phase 4: Generate Compliance Reports (Scheduled Task)

Management command to generate compliance reports for:
- Daily audit trail summaries
- Weekly data access analysis
- Monthly integrity checks

Usage:
    python manage.py generate_compliance_reports [--daily] [--weekly] [--monthly]
    
Typical cron setup (APScheduler or Celery Beat):
    Daily: 0 1 * * * (1 AM every day)
    Weekly: 0 2 * * 0 (2 AM every Sunday)
    Monthly: 0 3 1 * * (3 AM on the 1st)
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db.models import Count, Q

from apps.compliance.models_audit import (
    AuditLog, ComplianceReport, AccessLog, UserActivitySession
)
from apps.accounts.models import User


class Command(BaseCommand):
    help = "Generate scheduled compliance reports (daily, weekly, monthly)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--daily',
            action='store_true',
            help='Generate daily audit trail summary'
        )
        parser.add_argument(
            '--weekly',
            action='store_true',
            help='Generate weekly data access analysis'
        )
        parser.add_argument(
            '--monthly',
            action='store_true',
            help='Generate monthly integrity check'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Generate all report types'
        )

    def handle(self, *args, **options):
        self.stdout.write("Phase 4: Generating Compliance Reports")
        self.stdout.write("=" * 60)

        if options['all'] or options['daily']:
            self._generate_daily_audit()

        if options['all'] or options['weekly']:
            self._generate_weekly_access()

        if options['all'] or options['monthly']:
            self._generate_monthly_integrity()

        self.stdout.write(self.style.SUCCESS("Report generation complete!"))

    def _generate_daily_audit(self):
        """Generate daily audit trail summary."""
        now = timezone.now()
        yesterday = now - timedelta(days=1)
        start_of_day = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Collect daily audit statistics
        audit_logs = AuditLog.objects.filter(
            timestamp__gte=start_of_day,
            timestamp__lt=end_of_day
        )

        stats = {
            'total_actions': audit_logs.count(),
            'by_action': dict(audit_logs.values('action').annotate(
                count=Count('id')
            ).values_list('action', 'count')),
            'by_user': dict(audit_logs.values('user__username').annotate(
                count=Count('id')
            ).values_list('user__username', 'count')),
            'by_sensitivity': dict(audit_logs.values('sensitivity').annotate(
                count=Count('id')
            ).values_list('sensitivity', 'count')),
            'critical_actions': audit_logs.filter(
                sensitivity='CRITICAL'
            ).count(),
        }

        # Create ComplianceReport
        try:
            report = ComplianceReport.objects.create(
                report_type='AUDIT_TRAIL',
                start_date=start_of_day.date(),
                end_date=end_of_day.date(),
                generated_by=None,  # System-generated
                summary=f"Daily audit summary: {stats['total_actions']} actions, "
                        f"{stats['critical_actions']} critical",
                details=stats,
            )
            self.stdout.write(
                self.style.SUCCESS(f"✓ Daily audit report created: {stats['total_actions']} actions")
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Failed to create daily audit report: {e}"))

    def _generate_weekly_access(self):
        """Generate weekly data access analysis."""
        now = timezone.now()
        week_ago = now - timedelta(days=7)

        # Collect access statistics
        access_logs = AccessLog.objects.filter(
            timestamp__gte=week_ago
        )

        total_access = access_logs.count()
        successful = access_logs.filter(status='200').count()
        failed = access_logs.exclude(status='200').count()

        success_rate = (successful/total_access*100) if total_access > 0 else 0
        failure_rate = (failed/total_access*100) if total_access > 0 else 0

        stats = {
            'total_access': total_access,
            'successful': successful,
            'failed': failed,
            'success_rate': f"{success_rate:.1f}%",
            'by_type': dict(access_logs.values('access_type').annotate(
                count=Count('id')
            ).values_list('access_type', 'count')),
            'by_user': dict(access_logs.values('user__username').annotate(
                count=Count('id')
            ).values_list('user__username', 'count')),
            'top_resources': list(access_logs.values('resource').annotate(
                count=Count('id')
            ).order_by('-count')[:5].values_list('resource', 'count')),
        }

        # Create ComplianceReport
        try:
            report = ComplianceReport.objects.create(
                report_type='DATA_ACCESS',
                start_date=week_ago.date(),
                end_date=now.date(),
                generated_by=None,
                summary=f"Weekly access analysis: {total_access} accesses, "
                        f"{failed} failures ({failure_rate:.1f}%)",
                details=stats,
            )
            self.stdout.write(
                self.style.SUCCESS(f"✓ Weekly access report created: {total_access} accesses")
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Failed to create weekly access report: {e}"))

    def _generate_monthly_integrity(self):
        """Generate monthly data integrity check."""
        now = timezone.now()
        month_ago = now - timedelta(days=30)

        issues = []
        fixes = []

        # Check for users with no audit logs
        users_without_audit = list(
            User.objects.exclude(
                id__in=AuditLog.objects.values_list('user_id', flat=True)
            ).exclude(is_superuser=True).values_list('username', flat=True)
        )

        if users_without_audit:
            issues.append({
                'type': 'MISSING_AUDIT',
                'count': len(users_without_audit),
                'users': users_without_audit[:10]
            })

        # Check for orphaned sessions
        orphaned_sessions = UserActivitySession.objects.filter(user__isnull=True).count()
        if orphaned_sessions > 0:
            issues.append({
                'type': 'ORPHANED_SESSIONS',
                'count': orphaned_sessions
            })
            # Attempt to fix: delete orphaned sessions
            try:
                deleted = UserActivitySession.objects.filter(user__isnull=True).delete()[0]
                fixes.append(f"Deleted {deleted} orphaned sessions")
            except Exception as e:
                fixes.append(f"Failed to delete orphaned sessions: {e}")

        # Check suspicious activities
        suspicious = UserActivitySession.objects.filter(
            is_suspicious=True,
            login_timestamp__gte=month_ago
        ).count()

        if suspicious > 0:
            issues.append({
                'type': 'SUSPICIOUS_SESSIONS',
                'count': suspicious
            })

        stats = {
            'issues_found': len(issues),
            'issues': issues,
            'fixes_applied': fixes,
            'integrity_score': f"{max(0, 100 - len(issues)*5)}%"
        }

        # Create ComplianceReport
        try:
            report = ComplianceReport.objects.create(
                report_type='INTEGRITY_CHECK',
                start_date=month_ago.date(),
                end_date=now.date(),
                generated_by=None,
                summary=f"Monthly integrity check: {len(issues)} issues found, "
                        f"Integrity score: {stats['integrity_score']}",
                details=stats,
            )
            self.stdout.write(
                self.style.SUCCESS(f"✓ Monthly integrity report created: {len(issues)} issues")
            )
            for fix in fixes:
                self.stdout.write(self.style.SUCCESS(f"  → {fix}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"✗ Failed to create monthly integrity report: {e}"))
