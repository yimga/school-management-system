"""
Context processors for dashboard header/footer components.
Provides role-based data, system information, and metrics for templates.
"""
from datetime import datetime
from django.conf import settings
from django.utils import timezone
from apps.siteconfig.models import SiteSettings


def dashboard_context(request):
    """
    Provides dashboard header/footer context including:
    - Current timestamp
    - System version
    - Role-based metrics
    - User information
    """
    context = {
        'current_time': timezone.now(),
        'system_version': getattr(settings, 'APP_VERSION', '3.2.1'),
    }
    
    if not request.user.is_authenticated:
        return context
    
    user = request.user
    role = user.role
    
    # Role-specific metrics
    try:
        if role in ['ADMIN', 'LEADERSHIP', 'PRINCIPAL', 'VICE_PRINCIPAL', 'DEAN']:
            # Admin/Leadership metrics
            from apps.people.models import StudentProfile, TeacherProfile
            from apps.finance.models import Invoice
            
            context['total_students'] = StudentProfile.objects.filter(is_active=True).count()
            context['total_teachers'] = TeacherProfile.objects.filter(is_active=True).count()
            
            # Pending invoices
            pending_invoices = Invoice.objects.filter(status__in=['PENDING', 'PARTIAL'])
            context['pending_amount'] = sum(inv.balance or 0 for inv in pending_invoices)
            
        elif role == 'TEACHER':
            # Teacher metrics
            try:
                teacher_profile = user.teacher_profile
                classrooms = teacher_profile.classrooms.all()
                
                # Count students across all classrooms
                from apps.people.models import StudentProfile
                context['teacher_student_count'] = StudentProfile.objects.filter(
                    classroom__in=classrooms,
                    is_active=True
                ).count()
                
                context['teacher_class_count'] = classrooms.count()
                
                # Pending tasks (grades not entered, attendance not marked, etc.)
                from apps.evals.models import Assessment
                from apps.attendance.models import TeacherAttendance
                
                # Count assessments without grades
                pending_assessments = Assessment.objects.filter(
                    subject__teachers=teacher_profile,
                    is_published=False
                ).count()
                
                # Count days without attendance
                today = timezone.now().date()
                attendance_today = TeacherAttendance.objects.filter(
                    teacher=teacher_profile,
                    date=today
                ).exists()
                
                context['teacher_pending_tasks'] = pending_assessments + (0 if attendance_today else 1)
                
            except AttributeError:
                context['teacher_student_count'] = 0
                context['teacher_class_count'] = 0
                context['teacher_pending_tasks'] = 0
        
        elif role == 'PARENT':
            # Parent metrics
            from apps.people.models import StudentGuardian, StudentProfile
            from apps.finance.models import Invoice
            from apps.attendance.models import StudentAttendance
            
            # Get children
            children = StudentProfile.objects.filter(
                studentguardian__guardian__user=user
            ).distinct()
            
            context['parent_children_count'] = children.count()
            
            if children.exists():
                # Average attendance across all children
                total_attendance = 0
                for child in children:
                    attendance_records = StudentAttendance.objects.filter(student=child)
                    if attendance_records.exists():
                        present_count = attendance_records.filter(status='PRESENT').count()
                        total_count = attendance_records.count()
                        if total_count > 0:
                            total_attendance += (present_count / total_count * 100)
                
                context['parent_avg_attendance'] = round(total_attendance / children.count()) if children.count() > 0 else 0
                
                # Total balance for all children
                invoices = Invoice.objects.filter(student__in=children, status__in=['PENDING', 'PARTIAL'])
                context['parent_balance'] = sum(inv.balance or 0 for inv in invoices)
            else:
                context['parent_avg_attendance'] = 0
                context['parent_balance'] = 0
        
        elif role == 'STUDENT':
            # Student metrics
            try:
                student_profile = user.student_profile
                from apps.attendance.models import StudentAttendance
                from apps.evals.models import MarkEntry
                
                # Attendance percentage
                attendance_records = StudentAttendance.objects.filter(student=student_profile)
                if attendance_records.exists():
                    present_count = attendance_records.filter(status='PRESENT').count()
                    total_count = attendance_records.count()
                    context['student_attendance'] = round((present_count / total_count) * 100) if total_count > 0 else 0
                else:
                    context['student_attendance'] = 0
                
                # Average grade
                marks = MarkEntry.objects.filter(
                    student=student_profile,
                    mark__isnull=False
                ).values_list('mark', flat=True)
                
                if marks:
                    context['student_average'] = round(sum(marks) / len(marks))
                else:
                    context['student_average'] = 0
                
                # Pending assignments/tasks
                from apps.academics.models import Assignment
                pending_assignments = Assignment.objects.filter(
                    classroom=student_profile.classroom,
                    due_date__gte=timezone.now(),
                    is_active=True
                ).count()
                
                context['student_pending'] = pending_assignments
                
            except AttributeError:
                context['student_attendance'] = 0
                context['student_average'] = 0
                context['student_pending'] = 0
    
    except Exception as e:
        # Log error but don't break the page
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error in dashboard_context: {e}")
    
    return context


def site_settings_context(request):
    """
    Provides site settings for use in templates.
    Caches the result to avoid repeated database queries.
    """
    try:
        site = SiteSettings.get_current()
        return {
            'SITE': site,
            'SITE_THEME': site.get_theme_vars() if hasattr(site, 'get_theme_vars') else {},
        }
    except Exception:
        return {
            'SITE': None,
            'SITE_THEME': {},
        }
