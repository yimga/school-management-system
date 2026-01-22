"""
Phase 9 Task 1: BI Reporting Services
Executive reporting, data aggregation, export generation
"""

from django.db import models, connection
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Count, Sum, Avg, Q
from datetime import timedelta, datetime
import csv
import json
from io import StringIO
from typing import Dict, List, Any, Optional


class ExecutiveReportingService:
    """Generate executive-level reports and dashboards"""
    
    @staticmethod
    def get_financial_summary(start_date: datetime, end_date: datetime) -> Dict:
        """Financial KPIs for executive dashboard"""
        from apps.finance.models import Invoice, Payment
        
        cache_key = f'exec_finance_{start_date.date()}_{end_date.date()}'
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        invoices = Invoice.objects.filter(
            created_at__range=[start_date, end_date]
        )
        
        payments = Payment.objects.filter(
            created_at__range=[start_date, end_date],
            status='COMPLETED'
        )
        
        summary = {
            'total_invoiced': invoices.aggregate(total=Sum('amount'))['total'] or 0,
            'total_collected': payments.aggregate(total=Sum('amount'))['total'] or 0,
            'outstanding': invoices.filter(status='PENDING').aggregate(total=Sum('amount'))['total'] or 0,
            'invoice_count': invoices.count(),
            'payment_count': payments.count(),
            'collection_rate': 0.0,
            'period_start': start_date.isoformat(),
            'period_end': end_date.isoformat(),
        }
        
        if summary['total_invoiced'] > 0:
            summary['collection_rate'] = (summary['total_collected'] / summary['total_invoiced']) * 100
        
        cache.set(cache_key, summary, 3600)
        return summary
    
    @staticmethod
    def get_academic_summary(academic_year_id: int, term_id: Optional[int] = None) -> Dict:
        """Academic performance KPIs"""
        from apps.evals.models import Evaluation
        from apps.people.models import Student
        from apps.academics.models import Classroom
        
        cache_key = f'exec_academic_{academic_year_id}_{term_id}'
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        evaluations = Evaluation.objects.filter(academic_year_id=academic_year_id)
        if term_id:
            evaluations = evaluations.filter(term_id=term_id)
        
        students = Student.objects.filter(is_active=True)
        classrooms = Classroom.objects.filter(academic_year_id=academic_year_id)
        
        summary = {
            'total_students': students.count(),
            'total_classrooms': classrooms.count(),
            'total_evaluations': evaluations.count(),
            'average_score': evaluations.aggregate(avg=Avg('final_score'))['avg'] or 0,
            'pass_rate': 0.0,
            'excellence_rate': 0.0,
        }
        
        if evaluations.exists():
            passing = evaluations.filter(final_score__gte=50).count()
            excellent = evaluations.filter(final_score__gte=75).count()
            total = evaluations.count()
            
            summary['pass_rate'] = (passing / total) * 100 if total > 0 else 0
            summary['excellence_rate'] = (excellent / total) * 100 if total > 0 else 0
        
        cache.set(cache_key, summary, 1800)
        return summary
    
    @staticmethod
    def get_enrollment_trends(months: int = 12) -> Dict:
        """Enrollment trends over time"""
        from apps.people.models import Student
        
        cache_key = f'enrollment_trends_{months}'
        cached = cache.get(cache_key)
        if cached:
            return cached
        
        end_date = timezone.now()
        start_date = end_date - timedelta(days=months * 30)
        
        # Monthly enrollment counts
        students = Student.objects.filter(
            created_at__range=[start_date, end_date]
        ).extra(
            select={'month': "date_trunc('month', created_at)"}
        ).values('month').annotate(count=Count('id')).order_by('month')
        
        trends = {
            'monthly_enrollment': list(students),
            'total_active': Student.objects.filter(is_active=True).count(),
            'total_inactive': Student.objects.filter(is_active=False).count(),
            'period_months': months,
        }
        
        cache.set(cache_key, trends, 7200)
        return trends


class AdHocReportBuilder:
    """Build and execute custom reports"""
    
    ALLOWED_MODELS = {
        'students': 'apps.people.models.Student',
        'teachers': 'apps.people.models.Teacher',
        'invoices': 'apps.finance.models.Invoice',
        'payments': 'apps.finance.models.Payment',
        'evaluations': 'apps.evals.models.Evaluation',
        'classrooms': 'apps.academics.models.Classroom',
    }
    
    @staticmethod
    def execute_query(model_name: str, filters: Dict, fields: List[str]) -> List[Dict]:
        """Execute filtered query on allowed models"""
        if model_name not in AdHocReportBuilder.ALLOWED_MODELS:
            raise ValueError(f"Model {model_name} not allowed")
        
        from django.apps import apps
        
        app_label, model = AdHocReportBuilder.ALLOWED_MODELS[model_name].rsplit('.', 1)
        ModelClass = apps.get_model(app_label.split('.')[-1], model)
        
        queryset = ModelClass.objects.all()
        
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
        'FINANCE': 3600,      # 1 hour
        'ACADEMIC': 1800,     # 30 minutes
        'ATTENDANCE': 900,    # 15 minutes
        'ENROLLMENT': 7200,   # 2 hours
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
        
        # Cache result
        duration = ReportCacheManager.CACHE_DURATIONS.get(report_type, 3600)
        cache.set(cache_key, result, duration)
        
        # Store in database for long-term reference
        ReportCacheManager._store_materialized(cache_key, report_type, result, parameters, duration)
        
        return result
    
    @staticmethod
    def _build_cache_key(report_type: str, parameters: Dict) -> str:
        """Build unique cache key"""
        params_str = json.dumps(parameters, sort_keys=True)
        return f'report:{report_type}:{hash(params_str)}'
    
    @staticmethod
    def _store_materialized(cache_key: str, report_type: str, data: Any, 
                           parameters: Dict, duration: int):
        """Store materialized report in database"""
        from apps.reports.bi_models import MaterializedReportCache
        
        expires_at = timezone.now() + timedelta(seconds=duration)
        
        MaterializedReportCache.objects.update_or_create(
            cache_key=cache_key,
            defaults={
                'report_type': report_type,
                'data': data if isinstance(data, dict) else {'result': str(data)},
                'parameters': parameters,
                'row_count': len(data) if isinstance(data, (list, dict)) else 0,
                'expires_at': expires_at,
            }
        )
    
    @staticmethod
    def invalidate_report_cache(report_type: str):
        """Invalidate all caches for a report type"""
        from apps.reports.bi_models import MaterializedReportCache
        
        MaterializedReportCache.objects.filter(report_type=report_type).delete()
        
        # Clear memory cache (pattern-based)
        cache.delete_pattern(f'report:{report_type}:*')


class ScheduledReportRunner:
    """Execute scheduled reports"""
    
    @staticmethod
    def run_due_reports():
        """Run all reports that are due"""
        from apps.reports.bi_models import ScheduledReport, ReportExecution
        
        due_reports = ScheduledReport.objects.filter(
            is_active=True,
            next_run__lte=timezone.now()
        )
        
        for scheduled in due_reports:
            try:
                execution = ReportExecution.objects.create(
                    report_definition=scheduled.report_definition,
                    executed_by=scheduled.created_by,
                    parameters=scheduled.parameters,
                    status='RUNNING',
                    started_at=timezone.now()
                )
                
                # Execute report
                result = ScheduledReportRunner._execute_report(
                    scheduled.report_definition,
                    scheduled.parameters
                )
                
                execution.status = 'COMPLETED'
                execution.result_data = result
                execution.completed_at = timezone.now()
                execution.execution_time_ms = int(
                    (execution.completed_at - execution.started_at).total_seconds() * 1000
                )
                execution.save()
                
                # Send report to recipients
                ScheduledReportRunner._send_report(scheduled, result)
                
                # Update next run time
                scheduled.last_run = timezone.now()
                scheduled.next_run = ScheduledReportRunner._calculate_next_run(
                    scheduled.schedule_frequency,
                    scheduled.schedule_time
                )
                scheduled.save()
                
            except Exception as e:
                execution.status = 'FAILED'
                execution.error_message = str(e)
                execution.completed_at = timezone.now()
                execution.save()
    
    @staticmethod
    def _execute_report(report_definition, parameters: Dict) -> Dict:
        """Execute report definition"""
        # Placeholder - implement based on report_definition.query_template
        return {'status': 'executed', 'parameters': parameters}
    
    @staticmethod
    def _send_report(scheduled_report, result: Dict):
        """Send report via email"""
        from django.core.mail import send_mail
        
        subject = f"Scheduled Report: {scheduled_report.report_definition.name}"
        message = f"Report generated at {timezone.now()}\n\n{json.dumps(result, indent=2)}"
        
        send_mail(
            subject,
            message,
            'reports@school.local',
            scheduled_report.recipients,
            fail_silently=True
        )
    
    @staticmethod
    def _calculate_next_run(frequency: str, schedule_time) -> datetime:
        """Calculate next run time based on frequency"""
        now = timezone.now()
        next_run = now.replace(hour=schedule_time.hour, minute=schedule_time.minute, second=0)
        
        if frequency == 'DAILY':
            if next_run <= now:
                next_run += timedelta(days=1)
        elif frequency == 'WEEKLY':
            next_run += timedelta(days=7)
        elif frequency == 'MONTHLY':
            next_run += timedelta(days=30)
        elif frequency == 'QUARTERLY':
            next_run += timedelta(days=90)
        
        return next_run
