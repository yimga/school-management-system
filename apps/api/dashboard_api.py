# apps/api/dashboard_api.py
"""
Dashboard Overview APIs
Location: apps/api/dashboard_api.py

Provides unified dashboard data for all user roles
"""

from django.views import View
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)


@method_decorator(login_required, name='dispatch')
class AdminDashboardOverviewAPI(View):
    """Admin dashboard overview metrics"""
    
    def get(self, request):
        # Check admin permission
        if not (request.user.is_staff or request.user.role == 'ADMIN'):
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        try:
            from apps.people.models import StudentProfile, TeacherProfile
            from apps.finance.models import Invoice, Payment
            from apps.academics.models import Attendance
            
            # Calculate metrics
            total_students = StudentProfile.objects.filter(is_active=True).count()
            total_teachers = TeacherProfile.objects.filter(is_active=True).count()
            total_parents = 0  # Implement based on your parent model
            
            # Finance data
            total_invoices = Invoice.objects.aggregate(Sum('amount'))['amount__sum'] or 0
            total_paid = Payment.objects.aggregate(Sum('amount'))['amount__sum'] or 0
            pending_fees = total_invoices - total_paid
            
            # Attendance
            today = timezone.now().date()
            attendance_today = Attendance.objects.filter(date=today, status='present').count()
            attendance_rate = 0
            if total_students > 0:
                attendance_rate = (attendance_today / total_students) * 100
            
            # Active users today
            from django.contrib.auth.models import User
            last_24h = timezone.now() - timedelta(hours=24)
            active_users = User.objects.filter(last_login__gte=last_24h).count()
            
            return JsonResponse({
                'total_students': total_students,
                'total_teachers': total_teachers,
                'total_parents': total_parents,
                'total_revenue': float(total_paid),
                'pending_fees': float(pending_fees),
                'attendance_rate': round(attendance_rate, 1),
                'active_users_today': active_users,
                'system_health': 'healthy',
                'last_updated': timezone.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"Dashboard API error: {e}")
            return JsonResponse({'error': str(e)}, status=500)


@method_decorator(login_required, name='dispatch')
class TeacherDashboardAPI(View):
    """Teacher dashboard summary"""
    
    def get(self, request):
        if request.user.role != 'TEACHER':
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        try:
            from apps.people.models import TeacherProfile
            from apps.academics.models import Classroom
            
            teacher = TeacherProfile.objects.get(user=request.user)
            
            # Get teacher's classes
            my_classes = Classroom.objects.filter(teacher=teacher).count()
            
            # Get total students
            my_students = 0
            for classroom in Classroom.objects.filter(teacher=teacher):
                my_students += classroom.student_set.filter(is_active=True).count()
            
            # Pending grades (implement based on your assessment model)
            pending_grades = 0
            
            # Ungraded submissions (implement based on your submission model)
            ungraded_submissions = 0
            
            # Calculate class average
            class_average = 0.0
            
            return JsonResponse({
                'my_students': my_students,
                'my_classes': my_classes,
                'pending_grades': pending_grades,
                'ungraded_submissions': ungraded_submissions,
                'class_average': class_average,
                'last_updated': timezone.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"Teacher dashboard error: {e}")
            return JsonResponse({'error': str(e)}, status=500)


@method_decorator(login_required, name='dispatch')
class ParentDashboardAPI(View):
    """Parent dashboard summary"""
    
    def get(self, request):
        if request.user.role != 'PARENT':
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        try:
            from apps.people.models import StudentGuardian
            from apps.finance.models import Invoice, Payment
            
            # Get parent's children
            children = StudentGuardian.objects.filter(
                guardian__user=request.user,
                student__is_active=True
            ).values_list('student_id', flat=True)
            
            children_count = len(children)
            
            # Get pending fees for children
            total_invoices = Invoice.objects.filter(
                student_id__in=children
            ).aggregate(Sum('amount'))['amount__sum'] or 0
            
            total_paid = Payment.objects.filter(
                invoice__student_id__in=children
            ).aggregate(Sum('amount'))['amount__sum'] or 0
            
            pending_fees = total_invoices - total_paid
            
            # Messages unread
            from apps.communication.models import Message
            unread_messages = Message.objects.filter(
                recipient=request.user,
                is_read=False
            ).count()
            
            return JsonResponse({
                'children_count': children_count,
                'total_pending_fees': float(pending_fees),
                'messages_unread': unread_messages,
                'upcoming_events': 0,  # Implement based on your event model
                'last_updated': timezone.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"Parent dashboard error: {e}")
            return JsonResponse({'error': str(e)}, status=500)


@method_decorator(login_required, name='dispatch')
class StudentDashboardAPI(View):
    """Student dashboard summary"""
    
    def get(self, request):
        if request.user.role != 'STUDENT':
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        try:
            from apps.people.models import StudentProfile
            from apps.academics.models import Attendance, Classroom
            from apps.evals.models import Evaluation  # Adjust based on your model
            
            student = StudentProfile.objects.get(user=request.user)
            
            # Current classes
            current_classes = Classroom.objects.filter(
                level=student.current_class
            ).count()
            
            # Attendance percentage
            total_attendance = Attendance.objects.filter(student=student).count()
            present_days = Attendance.objects.filter(
                student=student,
                status='present'
            ).count()
            
            attendance_percentage = 0
            if total_attendance > 0:
                attendance_percentage = (present_days / total_attendance) * 100
            
            # Average grade
            average_grade = 0.0  # Implement based on your evaluation model
            
            # Pending assignments
            pending_assignments = 0  # Implement based on your assignment model
            
            return JsonResponse({
                'attendance_percentage': round(attendance_percentage, 1),
                'average_grade': average_grade,
                'pending_assignments': pending_assignments,
                'current_classes': current_classes,
                'last_updated': timezone.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"Student dashboard error: {e}")
            return JsonResponse({'error': str(e)}, status=500)


@method_decorator(login_required, name='dispatch')
class FinancialDashboardAPI(View):
    """Financial overview dashboard"""
    
    def get(self, request):
        if not (request.user.is_staff or request.user.role in ['ADMIN', 'BURSAR', 'LEADERSHIP']):
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        try:
            from apps.finance.models import Invoice, Payment
            
            # Total revenue
            total_revenue = Payment.objects.aggregate(Sum('amount'))['amount__sum'] or 0
            
            # Outstanding fees
            total_invoiced = Invoice.objects.aggregate(Sum('amount'))['amount__sum'] or 0
            outstanding = total_invoiced - total_revenue
            
            # Payment breakdown by method
            from apps.finance.models import PaymentMethod
            payment_methods = Payment.objects.values(
                'payment_method'
            ).annotate(total=Sum('amount')).order_by('-total')
            
            # Invoices by status
            invoices_by_status = Invoice.objects.values(
                'status'
            ).annotate(count=Count('id'))
            
            return JsonResponse({
                'total_revenue': float(total_revenue),
                'outstanding_fees': float(outstanding),
                'collection_rate': (total_revenue / total_invoiced * 100) if total_invoiced > 0 else 0,
                'payment_methods': list(payment_methods),
                'invoices_by_status': list(invoices_by_status),
                'last_updated': timezone.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"Financial dashboard error: {e}")
            return JsonResponse({'error': str(e)}, status=500)


@method_decorator(login_required, name='dispatch')
class AcademicDashboardAPI(View):
    """Academic performance dashboard"""
    
    def get(self, request):
        if not (request.user.is_staff or request.user.role in ['ADMIN', 'LEADERSHIP', 'HOD']):
            return JsonResponse({'error': 'Permission denied'}, status=403)
        
        try:
            from apps.academics.models import Classroom
            from apps.evals.models import Evaluation
            
            # Total classes
            total_classes = Classroom.objects.filter(is_active=True).count()
            
            # Average class performance
            avg_performance = 0.0  # Implement based on your evaluation model
            
            # Students at risk (low attendance or grades)
            students_at_risk = 0  # Implement based on your criteria
            
            # Attendance rate by class
            attendance_by_class = {}  # Implement calculation
            
            return JsonResponse({
                'total_classes': total_classes,
                'average_performance': avg_performance,
                'students_at_risk': students_at_risk,
                'attendance_summary': attendance_by_class,
                'last_updated': timezone.now().isoformat(),
            })
        except Exception as e:
            logger.error(f"Academic dashboard error: {e}")
            return JsonResponse({'error': str(e)}, status=500)
