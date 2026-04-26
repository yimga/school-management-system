"""
Context processors for dashboard header/footer components.
Provides role-based data, system information, and metrics for templates.
"""

import logging
import re
from decimal import Decimal
from django.conf import settings
from django.db import DatabaseError, connection, models, transaction
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _
from django.utils import timezone
from apps.platform_runtime.site_settings_read_access import get_effective_site_settings

logger = logging.getLogger(__name__)

CONTEXT_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    NoReverseMatch,
    RuntimeError,
    TypeError,
    ValueError,
)
DB_STATE_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    RuntimeError,
    TypeError,
    ValueError,
)


def _reset_db_state() -> None:
    """Clear broken transaction state after a DatabaseError."""
    try:
        if connection.in_atomic_block:
            transaction.set_rollback(False)
        elif connection.needs_rollback:
            connection.rollback()
    except DB_STATE_SOFT_FAILURES:
        pass


def dashboard_context(request):
    """
    Provides dashboard header/footer context including:
    - Current timestamp
    - System version
    - Role-based metrics
    - User information
    - tenant_path_prefix for Option A path-based tenant links (e.g. /t/default-school/)
    """
    try:
        from apps.schools.tenant_url import get_tenant_prefix

        tenant_prefix = get_tenant_prefix(request)
    except CONTEXT_SOFT_FAILURES:
        tenant_prefix = ""
    context = {
        "current_time": timezone.now(),
        "system_version": getattr(settings, "APP_VERSION", "3.2.1"),
        "can_customize_dashboard": False,
        "can_create_school_wide_announcement": False,
        "can_access_school_wide_announcement_create": False,
        "tenant_path_prefix": tenant_prefix,
        "simple_mode": False,  # Plan XIV: simplified UI; set from UserPreference below when authenticated
    }

    user = getattr(request, "user", None)
    if not getattr(user, "is_authenticated", False):
        return context
    if not getattr(user, "pk", None):
        return context

    if connection.needs_rollback:
        _reset_db_state()
        return context

    # Plan XIV: simple_mode from UserPreference (consumer-grade simplified UI)
    try:
        prefs = getattr(user, "preferences", None)
        context["simple_mode"] = bool(getattr(prefs, "simple_mode", False))
    except CONTEXT_SOFT_FAILURES:
        context["simple_mode"] = False

    try:
        from apps.communication.views_announcements import (
            _can_create_school_wide_announcement,
            _can_access_school_wide_announcement_create,
        )

        context["can_create_school_wide_announcement"] = (
            _can_create_school_wide_announcement(user)
        )
        context["can_access_school_wide_announcement_create"] = (
            _can_access_school_wide_announcement_create(user)
        )
    except CONTEXT_SOFT_FAILURES:
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
    except CONTEXT_SOFT_FAILURES:
        notifications_unread = 0

    try:
        from apps.communication.models import Message

        messages_unread_count = Message.objects.filter(
            recipient=user,
            is_read=False,
            is_archived=False,
        ).count()
    except CONTEXT_SOFT_FAILURES:
        messages_unread_count = 0

    context["messages_unread_count"] = messages_unread_count

    # RBAC: can user customize dashboard layout? (staff, ADMIN, LEADERSHIP, IT_ADMIN, SUPERADMIN only)
    try:
        from apps.siteconfig.dashboard_views import _can_customize

        context["can_customize_dashboard"] = _can_customize(user)
        # Dashboard Layout: only Backend supports customization; always link there
        context["dashboard_layout_link"] = (
            reverse("accounts:backend_dashboard") + "?customize=1"
        )
    except CONTEXT_SOFT_FAILURES:
        context["can_customize_dashboard"] = False
        try:
            context["dashboard_layout_link"] = (
                reverse("accounts:backend_dashboard") + "?customize=1"
            )
        except CONTEXT_SOFT_FAILURES:
            context["dashboard_layout_link"] = "/authentication/backend/?customize=1"

    # Role-specific metrics
    try:
        if role_value in ["ADMIN", "LEADERSHIP", "PRINCIPAL", "VICE_PRINCIPAL", "DEAN"]:
            # Admin/Leadership metrics
            from apps.people.models import StudentProfile, TeacherProfile

            context["total_students"] = StudentProfile.objects.filter(
                is_active=True
            ).count()
            context["total_teachers"] = TeacherProfile.objects.count()

            # Executive dashboard: Principal (and optionally Vice Principal) see no Bursar/accounting data
            if role_value not in ("PRINCIPAL", "VICE_PRINCIPAL"):
                from apps.finance.models import Invoice
                from django.db.models import Sum, DecimalField
                from django.db.models.functions import Coalesce

                _inv_qs = Invoice.objects.filter(status__in=["PENDING", "PARTIAL"])
                _inv_agg = _inv_qs.aggregate(
                    total=Coalesce(
                        Sum("balance_amount"), Decimal("0"), output_field=DecimalField()
                    )
                )
                context["pending_amount"] = _inv_agg["total"]
                context["pending_invoices_count"] = _inv_qs.count()
                context["dashboard_stats_cards"] = [
                    stat_card("Students", context.get("total_students", 0), "blue"),
                    stat_card("Teachers", context.get("total_teachers", 0), "green"),
                    stat_card(
                        "Pending", context.get("pending_invoices_count", 0), "pink"
                    ),
                    stat_card("Notifications", notifications_unread, "red"),
                ]
            else:
                # Principal / Vice Principal: executive view without finance
                context["dashboard_stats_cards"] = [
                    stat_card("Students", context.get("total_students", 0), "blue"),
                    stat_card("Teachers", context.get("total_teachers", 0), "green"),
                    stat_card("Notifications", notifications_unread, "red"),
                ]

        elif role_value == "TEACHER":
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
                context["teacher_class_count"] = len(classroom_ids)

                if assignment_pairs:
                    student_filters = models.Q()
                    for classroom_id, specialty_id in assignment_pairs:
                        if classroom_id and specialty_id:
                            student_filters |= models.Q(
                                classroom_id=classroom_id, specialty_id=specialty_id
                            )
                        elif classroom_id:
                            student_filters |= models.Q(classroom_id=classroom_id)
                    if active_year:
                        student_filters &= models.Q(academic_year=active_year)

                    context["teacher_student_count"] = (
                        StudentProfile.objects.filter(
                            student_filters,
                            is_active=True,
                        )
                        .distinct()
                        .count()
                    )
                else:
                    context["teacher_student_count"] = 0

                # Pending tasks (grades not entered, attendance not marked, etc.)
                try:
                    from apps.people.models import TeacherAttendance

                    eval_qs = Evaluation.objects.filter(teacher=teacher_profile)
                    if active_year:
                        eval_qs = eval_qs.filter(academic_year=active_year)
                    pending_assessments = eval_qs.filter(
                        models.Q(seq1_score__isnull=True)
                        | models.Q(seq2_score__isnull=True)
                        | models.Q(exam_score__isnull=True)
                    ).count()

                    today = timezone.now().date()
                    attendance_today = TeacherAttendance.objects.filter(
                        teacher=teacher_profile, date=today
                    ).exists()

                    context["teacher_pending_tasks"] = pending_assessments + (
                        0 if attendance_today else 1
                    )
                except CONTEXT_SOFT_FAILURES:
                    eval_qs = Evaluation.objects.filter(teacher=teacher_profile)
                    if active_year:
                        eval_qs = eval_qs.filter(academic_year=active_year)
                    context["teacher_pending_tasks"] = eval_qs.filter(
                        models.Q(seq1_score__isnull=True)
                        | models.Q(seq2_score__isnull=True)
                        | models.Q(exam_score__isnull=True)
                    ).count()

            except AttributeError:
                context["teacher_student_count"] = 0
                context["teacher_class_count"] = 0
                context["teacher_pending_tasks"] = 0

            context["dashboard_stats_cards"] = [
                stat_card("Students", context.get("teacher_student_count", 0), "blue"),
                stat_card("Classes", context.get("teacher_class_count", 0), "green"),
                stat_card("Pending", context.get("teacher_pending_tasks", 0), "pink"),
                stat_card("Notifications", notifications_unread, "red"),
            ]

        elif role_value == "PARENT":
            # Parent metrics
            from apps.people.models import StudentProfile
            from apps.finance.models import Invoice

            # Get children
            children = StudentProfile.objects.filter(
                guardian_links__guardian_user=user
            ).distinct()

            context["parent_children_count"] = children.count()

            if children.exists():
                # Average attendance across all children
                try:
                    from apps.attendance.models import StudentAttendance

                    total_attendance = 0
                    for child in children:
                        attendance_records = StudentAttendance.objects.filter(
                            student=child
                        )
                        if attendance_records.exists():
                            present_count = attendance_records.filter(
                                status="PRESENT"
                            ).count()
                            total_count = attendance_records.count()
                            if total_count > 0:
                                total_attendance += present_count / total_count * 100

                    context["parent_avg_attendance"] = (
                        round(total_attendance / children.count())
                        if children.count() > 0
                        else 0
                    )
                except ImportError:
                    context["parent_avg_attendance"] = 0

                # Total balance for all children -- aggregate to avoid SELECTing all columns
                from django.db.models import Sum, DecimalField
                from django.db.models.functions import Coalesce

                _parent_agg = Invoice.objects.filter(
                    student__in=children, status__in=["PENDING", "PARTIAL"]
                ).aggregate(
                    total=Coalesce(
                        Sum("balance_amount"), Decimal("0"), output_field=DecimalField()
                    )
                )
                context["parent_balance"] = _parent_agg["total"]
            else:
                context["parent_avg_attendance"] = 0
                context["parent_balance"] = 0

            try:
                from apps.portal.portal_models import PortalNotification

                notifications_unread = PortalNotification.objects.filter(
                    parent_id=user.id,
                    is_read=False,
                ).count()
            except DatabaseError:
                _reset_db_state()
            except CONTEXT_SOFT_FAILURES:
                pass

            # Use view-provided attendance when on parent dashboard so top bar matches dashboard cards
            attendance_for_stat = getattr(
                request, "parent_dashboard_attendance_pct", None
            )
            if attendance_for_stat is None:
                attendance_for_stat = context.get("parent_avg_attendance", 0)
            context["dashboard_stats_cards"] = [
                stat_card("Children", context.get("parent_children_count", 0), "blue"),
                stat_card("Attendance", attendance_for_stat, "green", suffix="%"),
                stat_card(
                    "Balance", context.get("parent_balance", 0), "pink", prefix="$"
                ),
                stat_card("Notifications", notifications_unread, "red"),
            ]

        elif role_value == "STUDENT":
            # Student metrics
            try:
                student_profile = user.student_profile
                from apps.evals.models import MarkEntry

                # Attendance percentage (apps.academics.models.Attendance)
                try:
                    from apps.academics.models import Attendance

                    attendance_records = Attendance.objects.filter(
                        student=student_profile
                    )
                    if attendance_records.exists():
                        present_count = attendance_records.filter(
                            status=Attendance.Status.PRESENT
                        ).count()
                        total_count = attendance_records.count()
                        context["student_attendance"] = (
                            round((present_count / total_count) * 100)
                            if total_count > 0
                            else 0
                        )
                    else:
                        context["student_attendance"] = 0
                except CONTEXT_SOFT_FAILURES:
                    context["student_attendance"] = 0

                # Average grade
                marks = MarkEntry.objects.filter(
                    student=student_profile, mark__isnull=False
                ).values_list("mark", flat=True)

                if marks:
                    context["student_average"] = round(sum(marks) / len(marks))
                else:
                    context["student_average"] = 0

                # Pending assignments/tasks
                from apps.academics.models import Assignment

                pending_assignments = Assignment.objects.filter(
                    classroom=student_profile.classroom,
                    due_date__gte=timezone.now(),
                    is_active=True,
                ).count()

                context["student_pending"] = pending_assignments

            except AttributeError:
                context["student_attendance"] = 0
                context["student_average"] = 0
                context["student_pending"] = 0

            context["dashboard_stats_cards"] = [
                stat_card(
                    "Attendance",
                    context.get("student_attendance", 0),
                    "blue",
                    suffix="%",
                ),
                stat_card("Average", context.get("student_average", 0), "green"),
                stat_card("Pending", context.get("student_pending", 0), "pink"),
                stat_card("Notifications", notifications_unread, "red"),
            ]
        context["notifications_unread"] = notifications_unread

    except DatabaseError as e:
        _reset_db_state()
        logger.error(f"Database error in dashboard_context: {e}")
        context["notifications_unread"] = notifications_unread
    except CONTEXT_SOFT_FAILURES as e:
        # Log error but don't break the page
        logger.error(f"Error in dashboard_context: {e}")
        context["notifications_unread"] = notifications_unread

    return context


def site_settings_context(request):
    """
    Provides site settings for use in templates.
    Caches the result to avoid repeated database queries.
    """
    try:
        site = get_effective_site_settings(request=request)
        if site is None:
            return {}
        return {
            "SITE": site,
            "SITE_THEME": site.get_theme_vars()
            if hasattr(site, "get_theme_vars")
            else {},
        }
    except DatabaseError:
        _reset_db_state()
        return {
            "SITE": None,
            "SITE_THEME": {},
        }
    except CONTEXT_SOFT_FAILURES:
        return {
            "SITE": None,
            "SITE_THEME": {},
        }


_STUDENT_360_SIDEBAR_PATH = re.compile(r"/backend/students/(\d+)/?$")
_TEACHER_SIDEBAR_PATH = re.compile(r"/backend/teachers/(\d+)/?$")
_CLASSROOM_SIDEBAR_PATH = re.compile(r"/backend/classrooms/(\d+)/?$")


def sidebar_record_context(request):
    """
    Context rail: Student 360, teacher record, or classroom — quick links in sidebar.
    """
    out = {"sidebar_record_context": None}
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return out
    school = getattr(request, "school", None)
    if not school:
        return out
    path = getattr(request, "path", "") or ""

    m = _STUDENT_360_SIDEBAR_PATH.search(path)
    if m:
        try:
            sid = int(m.group(1))
        except ValueError:
            return out
        try:
            from apps.people.models import StudentProfile

            st = StudentProfile.objects.filter(pk=sid, school_id=school.id).first()
            if not st:
                return out
            links = []
            _link = links.append
            try:
                _link(
                    {
                        "label": _("Student 360"),
                        "url": reverse(
                            "accounts:backend_student_detail",
                            kwargs={"student_id": sid},
                        ),
                    }
                )
            except NoReverseMatch:
                pass
            try:
                _link({"label": _("Invoices"), "url": reverse("finance:invoices")})
            except NoReverseMatch:
                pass
            try:
                _link(
                    {
                        "label": _("Transcript archive"),
                        "url": reverse(
                            "portal:transcript_archive", kwargs={"student_id": sid}
                        ),
                    }
                )
            except NoReverseMatch:
                pass
            try:
                _link(
                    {
                        "label": _("Discipline incidents"),
                        "url": reverse("portal:discipline_incidents_list"),
                    }
                )
            except NoReverseMatch:
                pass
            try:
                _link(
                    {"label": _("Messages"), "url": reverse("accounts:user_messages")}
                )
            except NoReverseMatch:
                pass
            try:
                _link(
                    {
                        "label": _("Evaluations (admin)"),
                        "url": reverse("evals:evaluation_admin"),
                    }
                )
            except NoReverseMatch:
                pass
            try:
                _link(
                    {
                        "label": _("At-risk dashboard"),
                        "url": reverse("analytics:at_risk_dashboard"),
                    }
                )
            except NoReverseMatch:
                pass
            try:
                _link(
                    {
                        "label": _("Django admin record"),
                        "url": reverse(
                            "admin:people_studentprofile_change", args=[sid]
                        ),
                    }
                )
            except NoReverseMatch:
                pass
            out["sidebar_record_context"] = {
                "title": _("This student"),
                "subtitle": f"{st.first_name} {st.last_name}".strip(),
                "links": links,
            }
        except Exception as e:
            logger.debug("sidebar_record_context student: %s", e)
        return out

    m = _TEACHER_SIDEBAR_PATH.search(path)
    if m:
        try:
            tid = int(m.group(1))
        except ValueError:
            return out
        try:
            from apps.people.models import TeacherProfile

            tp = TeacherProfile.objects.filter(pk=tid).first()
            if not tp or (tp.school_id and tp.school_id != school.id):
                return out
            name = (
                tp.user.get_full_name().strip()
                or tp.user.username
                or (tp.staff_id or str(tp.pk))
            )
            links = []
            _link = links.append
            try:
                _link(
                    {
                        "label": _("Teacher overview"),
                        "url": reverse(
                            "accounts:backend_teacher_detail",
                            kwargs={"teacher_id": tid},
                        ),
                    }
                )
            except NoReverseMatch:
                pass
            try:
                _link(
                    {
                        "label": _("All teachers"),
                        "url": reverse("accounts:backend_teacher_list"),
                    }
                )
            except NoReverseMatch:
                pass
            try:
                _link(
                    {
                        "label": _("Take student attendance"),
                        "url": reverse("portal:take_student_attendance"),
                    }
                )
            except NoReverseMatch:
                pass
            try:
                _link(
                    {
                        "label": _("Teacher attendance"),
                        "url": reverse("portal:record_teacher_attendance"),
                    }
                )
            except NoReverseMatch:
                pass
            try:
                _link(
                    {"label": _("Messages"), "url": reverse("accounts:user_messages")}
                )
            except NoReverseMatch:
                pass
            try:
                _link(
                    {
                        "label": _("Django admin"),
                        "url": reverse(
                            "admin:people_teacherprofile_change", args=[tid]
                        ),
                    }
                )
            except NoReverseMatch:
                pass
            out["sidebar_record_context"] = {
                "title": _("This teacher"),
                "subtitle": name,
                "links": links,
            }
        except Exception as e:
            logger.debug("sidebar_record_context teacher: %s", e)
        return out

    m = _CLASSROOM_SIDEBAR_PATH.search(path)
    if m:
        try:
            cid = int(m.group(1))
        except ValueError:
            return out
        try:
            from apps.academics.models import Classroom

            room = Classroom.objects.filter(pk=cid, school_id=school.id).first()
            if not room:
                return out
            links = []
            _link = links.append
            try:
                _link(
                    {
                        "label": _("Class overview"),
                        "url": reverse(
                            "accounts:backend_classroom_detail",
                            kwargs={"classroom_id": cid},
                        ),
                    }
                )
            except NoReverseMatch:
                pass
            try:
                _link(
                    {
                        "label": _("Students in this class"),
                        "url": reverse("accounts:backend_student_list")
                        + f"?classroom={cid}",
                    }
                )
            except NoReverseMatch:
                pass
            try:
                _link(
                    {
                        "label": _("All classrooms"),
                        "url": reverse("accounts:backend_classroom_list"),
                    }
                )
            except NoReverseMatch:
                pass
            try:
                _link(
                    {
                        "label": _("Take student attendance"),
                        "url": reverse("portal:take_student_attendance"),
                    }
                )
            except NoReverseMatch:
                pass
            try:
                _link(
                    {
                        "label": _("At-risk dashboard"),
                        "url": reverse("analytics:at_risk_dashboard"),
                    }
                )
            except NoReverseMatch:
                pass
            try:
                _link(
                    {
                        "label": _("Django admin"),
                        "url": reverse("admin:academics_classroom_change", args=[cid]),
                    }
                )
            except NoReverseMatch:
                pass
            out["sidebar_record_context"] = {
                "title": _("This class"),
                "subtitle": room.name,
                "links": links,
            }
        except Exception as e:
            logger.debug("sidebar_record_context classroom: %s", e)
    return out
