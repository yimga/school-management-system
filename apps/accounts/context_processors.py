"""
Context processors for dashboard header/footer components.
Provides role-based data, system information, and metrics for templates.
"""
from decimal import Decimal
from django.conf import settings
from django.db import DatabaseError, connection, models, transaction
from django.utils import timezone
from apps.siteconfig.models import SiteSettings


def _reset_db_state() -> None:
    """Clear broken transaction state after a DatabaseError."""
    try:
        if connection.in_atomic_block:
            transaction.set_rollback(False)
        elif connection.needs_rollback:
            connection.rollback()
    except Exception:
        pass


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
        'can_customize_dashboard': False,
        'can_create_school_wide_announcement': False,
        'can_access_school_wide_announcement_create': False,
    }

    if not request.user.is_authenticated:
        return context

    if connection.needs_rollback:
        _reset_db_state()
        return context

    user = request.user
    try:
        from apps.communication.views_announcements import (
            _can_create_school_wide_announcement,
            _can_access_school_wide_announcement_create,
        )
        context['can_create_school_wide_announcement'] = _can_create_school_wide_announcement(user)
        context['can_access_school_wide_announcement_create'] = _can_access_school_wide_announcement_create(user)
    except Exception:
        pass
    role_value = (getattr(user, "role", "") or "").upper()

    def format_stat_value(value, prefix="", suffix=""):
        if value is None:
            value = 0
        if isinstance(value, Decimal):
            display = f"{value:,.2f}"
        elif isinstance(value, (int, float)):
            display = f"{value:,}"
        else:
            display = str(value)
        return f"{prefix}{display}{suffix}"

    def stat_card(label, value, tone, prefix="", suffix=""):
        tone_styles = {
            "blue": {
                "bg": "linear-gradient(135deg, rgba(102, 126, 234, 0.1), rgba(118, 75, 162, 0.08))",
                "border": "rgba(102, 126, 234, 0.2)",
                "badge": "#667eea",
                "badge_text": "#fff",
            },
            "green": {
                "bg": "linear-gradient(135deg, rgba(56, 161, 105, 0.1), rgba(56, 161, 105, 0.08))",
                "border": "rgba(56, 161, 105, 0.2)",
                "badge": "#38a169",
                "badge_text": "#fff",
            },
            "pink": {
                "bg": "linear-gradient(135deg, rgba(240, 147, 251, 0.1), rgba(245, 87, 108, 0.08))",
                "border": "rgba(240, 147, 251, 0.2)",
                "badge": "#f5576c",
                "badge_text": "#fff",
            },
            "red": {
                "bg": "linear-gradient(135deg, rgba(220, 53, 69, 0.1), rgba(220, 53, 69, 0.08))",
                "border": "rgba(220, 53, 69, 0.2)",
                "badge": "#dc3545",
                "badge_text": "#fff",
            },
        }
        style = tone_styles.get(tone, tone_styles["blue"])
        return {
            "label": label,
            "value": format_stat_value(value, prefix=prefix, suffix=suffix),
            "card_style": f"background: {style['bg']}; border: 1px solid {style['border']};",
            "badge_style": f"background: {style['badge']}; color: {style['badge_text']};",
        }

    notifications_unread = 0
    messages_unread_count = 0
    try:
        from apps.finance.models import Notification as FinanceNotification

        notifications_unread = FinanceNotification.objects.filter(
            recipient=user,
            is_read=False,
        ).count()
    except DatabaseError:
        _reset_db_state()
        notifications_unread = 0
    except Exception:
        notifications_unread = 0

    try:
        from apps.communication.models import Message
        messages_unread_count = Message.objects.filter(
            recipient=user,
            is_read=False,
            is_archived=False,
        ).count()
    except Exception:
        messages_unread_count = 0

    context["messages_unread_count"] = messages_unread_count

    # RBAC: can user customize dashboard layout? (staff, ADMIN, LEADERSHIP, IT_ADMIN, SUPERADMIN only)
    try:
        from django.urls import reverse
        from apps.siteconfig.dashboard_views import _can_customize
        context["can_customize_dashboard"] = _can_customize(user)
        # Dashboard Layout: only Backend supports customization; always link there
        context["dashboard_layout_link"] = reverse("accounts:backend_dashboard") + "?customize=1"
    except Exception:
        context["can_customize_dashboard"] = False
        try:
            from django.urls import reverse as _reverse
            context["dashboard_layout_link"] = _reverse("accounts:backend_dashboard") + "?customize=1"
        except Exception:
            context["dashboard_layout_link"] = "/authentication/backend/?customize=1"

    # Role-specific metrics
    try:
        if role_value in ['ADMIN', 'LEADERSHIP', 'PRINCIPAL', 'VICE_PRINCIPAL', 'DEAN']:
            # Admin/Leadership metrics
            from apps.people.models import StudentProfile, TeacherProfile
            
            context['total_students'] = StudentProfile.objects.filter(is_active=True).count()
            context['total_teachers'] = TeacherProfile.objects.count()
            
            # Executive dashboard: Principal (and optionally Vice Principal) see no Bursar/accounting data
            if role_value not in ('PRINCIPAL', 'VICE_PRINCIPAL'):
                from apps.finance.models import Invoice
                from django.db.models import Sum, DecimalField
                from django.db.models.functions import Coalesce
                _inv_qs = Invoice.objects.filter(status__in=['PENDING', 'PARTIAL'])
                _inv_agg = _inv_qs.aggregate(
                    total=Coalesce(Sum('balance_amount'), Decimal('0'), output_field=DecimalField())
                )
                context['pending_amount'] = _inv_agg['total']
                context['pending_invoices_count'] = _inv_qs.count()
                context['dashboard_stats_cards'] = [
                    stat_card("Students", context.get('total_students', 0), "blue"),
                    stat_card("Teachers", context.get('total_teachers', 0), "green"),
                    stat_card("Pending", context.get('pending_invoices_count', 0), "pink"),
                    stat_card("Notifications", notifications_unread, "red"),
                ]
            else:
                # Principal / Vice Principal: executive view without finance
                context['dashboard_stats_cards'] = [
                    stat_card("Students", context.get('total_students', 0), "blue"),
                    stat_card("Teachers", context.get('total_teachers', 0), "green"),
                    stat_card("Notifications", notifications_unread, "red"),
                ]
            
        elif role_value == 'TEACHER':
            # Teacher metrics
            try:
                teacher_profile = user.teacher_profile
                from apps.evals.models import TeacherAssignment, Evaluation
                from apps.people.models import StudentProfile
                from apps.academics.services import get_active_year_and_term

                active_year, _active_term = get_active_year_and_term()

                assignments = TeacherAssignment.objects.filter(
                    teacher=teacher_profile,
                    is_active=True,
                )
                if active_year:
                    assignments = assignments.filter(academic_year=active_year)

                assignment_pairs = list(
                    assignments.values_list(
                        "subject_assignment__classroom_id",
                        "subject_assignment__specialty_id",
                    ).distinct()
                )
                classroom_ids = {pair[0] for pair in assignment_pairs if pair[0]}
                context['teacher_class_count'] = len(classroom_ids)

                if assignment_pairs:
                    student_filters = models.Q()
                    for classroom_id, specialty_id in assignment_pairs:
                        if classroom_id and specialty_id:
                            student_filters |= models.Q(classroom_id=classroom_id, specialty_id=specialty_id)
                        elif classroom_id:
                            student_filters |= models.Q(classroom_id=classroom_id)
                    if active_year:
                        student_filters &= models.Q(academic_year=active_year)

                    context['teacher_student_count'] = StudentProfile.objects.filter(
                        student_filters,
                        is_active=True,
                    ).distinct().count()
                else:
                    context['teacher_student_count'] = 0

                # Pending tasks (grades not entered, attendance not marked, etc.)
                try:
                    from apps.people.models import TeacherAttendance

                    eval_qs = Evaluation.objects.filter(teacher=teacher_profile)
                    if active_year:
                        eval_qs = eval_qs.filter(academic_year=active_year)
                    pending_assessments = eval_qs.filter(
                        models.Q(seq1_score__isnull=True) |
                        models.Q(seq2_score__isnull=True) |
                        models.Q(exam_score__isnull=True)
                    ).count()

                    today = timezone.now().date()
                    attendance_today = TeacherAttendance.objects.filter(
                        teacher=teacher_profile,
                        date=today
                    ).exists()

                    context['teacher_pending_tasks'] = pending_assessments + (0 if attendance_today else 1)
                except Exception:
                    eval_qs = Evaluation.objects.filter(teacher=teacher_profile)
                    if active_year:
                        eval_qs = eval_qs.filter(academic_year=active_year)
                    context['teacher_pending_tasks'] = eval_qs.filter(
                        models.Q(seq1_score__isnull=True) |
                        models.Q(seq2_score__isnull=True) |
                        models.Q(exam_score__isnull=True)
                    ).count()

            except AttributeError:
                context['teacher_student_count'] = 0
                context['teacher_class_count'] = 0
                context['teacher_pending_tasks'] = 0

            context['dashboard_stats_cards'] = [
                stat_card("Students", context.get('teacher_student_count', 0), "blue"),
                stat_card("Classes", context.get('teacher_class_count', 0), "green"),
                stat_card("Pending", context.get('teacher_pending_tasks', 0), "pink"),
                stat_card("Notifications", notifications_unread, "red"),
            ]
        
        elif role_value == 'PARENT':
            # Parent metrics
            from apps.people.models import StudentProfile
            from apps.finance.models import Invoice
            
            # Get children
            children = StudentProfile.objects.filter(
                guardian_links__guardian_user=user
            ).distinct()
            
            context['parent_children_count'] = children.count()
            
            if children.exists():
                # Average attendance across all children
                try:
                    from apps.attendance.models import StudentAttendance
                    total_attendance = 0
                    for child in children:
                        attendance_records = StudentAttendance.objects.filter(student=child)
                        if attendance_records.exists():
                            present_count = attendance_records.filter(status='PRESENT').count()
                            total_count = attendance_records.count()
                            if total_count > 0:
                                total_attendance += (present_count / total_count * 100)
                    
                    context['parent_avg_attendance'] = round(total_attendance / children.count()) if children.count() > 0 else 0
                except ImportError:
                    context['parent_avg_attendance'] = 0
                
                # Total balance for all children -- aggregate to avoid SELECTing all columns
                from django.db.models import Sum, DecimalField
                from django.db.models.functions import Coalesce
                _parent_agg = Invoice.objects.filter(
                    student__in=children, status__in=['PENDING', 'PARTIAL']
                ).aggregate(
                    total=Coalesce(Sum('balance_amount'), Decimal('0'), output_field=DecimalField())
                )
                context['parent_balance'] = _parent_agg['total']
            else:
                context['parent_avg_attendance'] = 0
                context['parent_balance'] = 0

            try:
                from apps.portal.portal_models import PortalNotification

                notifications_unread = PortalNotification.objects.filter(
                    parent_id=user.id,
                    is_read=False,
                ).count()
            except DatabaseError:
                _reset_db_state()
            except Exception:
                pass

            # Use view-provided attendance when on parent dashboard so top bar matches dashboard cards
            attendance_for_stat = getattr(request, 'parent_dashboard_attendance_pct', None)
            if attendance_for_stat is None:
                attendance_for_stat = context.get('parent_avg_attendance', 0)
            context['dashboard_stats_cards'] = [
                stat_card("Children", context.get('parent_children_count', 0), "blue"),
                stat_card("Attendance", attendance_for_stat, "green", suffix="%"),
                stat_card("Balance", context.get('parent_balance', 0), "pink", prefix="$"),
                stat_card("Notifications", notifications_unread, "red"),
            ]
        
        elif role_value == 'STUDENT':
            # Student metrics
            try:
                student_profile = user.student_profile
                from apps.evals.models import MarkEntry
                
                # Attendance percentage (apps.academics.models.Attendance)
                try:
                    from apps.academics.models import Attendance
                    attendance_records = Attendance.objects.filter(student=student_profile)
                    if attendance_records.exists():
                        present_count = attendance_records.filter(status=Attendance.Status.PRESENT).count()
                        total_count = attendance_records.count()
                        context['student_attendance'] = round((present_count / total_count) * 100) if total_count > 0 else 0
                    else:
                        context['student_attendance'] = 0
                except Exception:
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

            context['dashboard_stats_cards'] = [
                stat_card("Attendance", context.get('student_attendance', 0), "blue", suffix="%"),
                stat_card("Average", context.get('student_average', 0), "green"),
                stat_card("Pending", context.get('student_pending', 0), "pink"),
                stat_card("Notifications", notifications_unread, "red"),
            ]
        context['notifications_unread'] = notifications_unread
    
    except DatabaseError as e:
        _reset_db_state()
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Database error in dashboard_context: {e}")
        context['notifications_unread'] = notifications_unread
    except Exception as e:
        # Log error but don't break the page
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error in dashboard_context: {e}")
        context['notifications_unread'] = notifications_unread
    
    return context


def site_settings_context(request):
    """
    Provides site settings for use in templates.
    Caches the result to avoid repeated database queries.
    """
    try:
        site = SiteSettings.get_solo()
        return {
            'SITE': site,
            'SITE_THEME': site.get_theme_vars() if hasattr(site, 'get_theme_vars') else {},
        }
    except DatabaseError:
        _reset_db_state()
        return {
            'SITE': None,
            'SITE_THEME': {},
        }
    except Exception:
        return {
            'SITE': None,
            'SITE_THEME': {},
        }
