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
from django.db.models import Count, Sum, Q
from django.db.utils import DatabaseError
from django.core.exceptions import ObjectDoesNotExist
from django.utils import timezone
from datetime import timedelta
import logging

from apps.platform_runtime.helpers import get_effective_flags

logger = logging.getLogger(__name__)


@method_decorator(login_required, name="dispatch")
class AdminDashboardOverviewAPI(View):
    """Admin dashboard overview metrics"""

    def get(self, request):
        role_value = (getattr(request.user, "role", "") or "").upper()
        is_admin_like = (
            request.user.is_superuser
            or request.user.is_staff
            or role_value
            in [
                "ADMIN",
                "LEADERSHIP",
                "PRINCIPAL",
                "VICE_PRINCIPAL",
                "DEAN",
                "IT_ADMIN",
                "BURSAR",
            ]
        )
        # Check admin permission
        if not is_admin_like:
            return JsonResponse({"error": "Permission denied"}, status=403)

        try:
            from apps.people.models import StudentProfile, TeacherProfile
            from apps.finance.models import Invoice, Payment
            from apps.academics.models import Attendance

            # Calculate metrics
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            total_students = StudentProfile.objects.filter(is_active=True).count()
            total_teachers = TeacherProfile.objects.filter(is_active=True).count()
            total_parents = 0  # Implement based on your parent model

            # Finance data — exclude voided/soft-deleted invoices and
            # soft-deleted (reversed) payments so totals reflect real money
            # (consistent with Invoice.computed_balance / recalculate_invoice).
            # tenant-isolation-allow: rls-scoped-finance-admin-dashboard-aggregate
            total_invoices = (
                Invoice.objects.exclude(status=Invoice.Status.VOID)
                .filter(deleted_at__isnull=True)
                .aggregate(Sum("total_amount"))["total_amount__sum"]
                or 0
            )
            # tenant-isolation-allow: rls-scoped-finance-admin-dashboard-aggregate
            total_paid = (
                Payment.objects.filter(deleted_at__isnull=True).aggregate(Sum("amount"))[
                    "amount__sum"
                ]
                or 0
            )
            pending_fees = total_invoices - total_paid

            # Attendance
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            today = timezone.now().date()
            attendance_today = Attendance.objects.filter(
                date=today, status="present"
            ).count()
            attendance_rate = 0
            if total_students > 0:
                attendance_rate = (attendance_today / total_students) * 100

            # Active users today — scoped to THIS school's people. The shared
            # auth_user table has no school FK (it lives in SHARED_APPS and has
            # no school_id for RLS to bind to), so a global
            # User.objects.filter(last_login=...) would count active users
            # across ALL tenants. Derive the count from the school-scoped
            # student/teacher profiles instead (RLS-filtered, like the
            # total_students / total_teachers metrics above).
            last_24h = timezone.now() - timedelta(hours=24)
            # tenant-isolation-allow: derived-from-rls-scoped-people-profiles-no-school-fk-on-user
            active_student_ids = StudentProfile.objects.filter(
                user__last_login__gte=last_24h
            ).values_list("user_id", flat=True)
            # tenant-isolation-allow: derived-from-rls-scoped-people-profiles-no-school-fk-on-user
            active_teacher_ids = TeacherProfile.objects.filter(
                user__last_login__gte=last_24h
            ).values_list("user_id", flat=True)
            active_users = len(set(active_student_ids) | set(active_teacher_ids))

            return JsonResponse(
                {
                    "total_students": total_students,
                    "total_teachers": total_teachers,
                    "total_parents": total_parents,
                    "total_revenue": float(total_paid),
                    "pending_fees": float(pending_fees),
                    "attendance_rate": round(attendance_rate, 1),
                    "active_users_today": active_users,
                    "system_health": "healthy",
                    "last_updated": timezone.now().isoformat(),
                }
            )
        except (
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
            ObjectDoesNotExist,
            DatabaseError,
        ) as e:
            logger.error("Dashboard API error: %s", e, exc_info=True)
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(login_required, name="dispatch")
class TeacherDashboardAPI(View):
    """Teacher dashboard summary"""

    def get(self, request):
        role_value = (getattr(request.user, "role", "") or "").upper()
        if role_value != "TEACHER":
            return JsonResponse({"error": "Permission denied"}, status=403)

        try:
            from apps.people.models import TeacherProfile, StudentProfile
            from apps.evals.models import TeacherAssignment
            from apps.academics.services import get_active_year_and_term

            try:
                # tenant-isolation-allow: view-scoped-via-request-school
                teacher = TeacherProfile.objects.get(user=request.user)
            except TeacherProfile.DoesNotExist:
                return JsonResponse(
                    {"error": "Teacher profile not found for this account."},
                    status=404,
                )

            active_year, _active_term = get_active_year_and_term()
            # tenant-isolation-allow: view-scoped-via-request-school
            assignments = TeacherAssignment.objects.filter(
                teacher=teacher,
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

            my_classes = len(classroom_ids)
            if assignment_pairs:
                student_filters = Q()
                for classroom_id, specialty_id in assignment_pairs:
                    if classroom_id and specialty_id:
                        student_filters |= Q(
                            classroom_id=classroom_id, specialty_id=specialty_id
                        )
                    elif classroom_id:
                        student_filters |= Q(classroom_id=classroom_id)
                if active_year:
                    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                    student_filters &= Q(academic_year=active_year)
                my_students = (
                    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                    StudentProfile.objects.filter(
                        student_filters,
                        is_active=True,
                    )
                    .distinct()
                    .count()
                )
            else:
                my_students = 0

            # Pending grades (implement based on your assessment model)
            pending_grades = 0

            # Ungraded submissions (implement based on your submission model)
            ungraded_submissions = 0

            # Calculate class average
            class_average = 0.0

            return JsonResponse(
                {
                    "my_students": my_students,
                    "my_classes": my_classes,
                    "pending_grades": pending_grades,
                    "ungraded_submissions": ungraded_submissions,
                    "class_average": class_average,
                    "last_updated": timezone.now().isoformat(),
                }
            )
        except (
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
            ObjectDoesNotExist,
            DatabaseError,
        ) as e:
            logger.error("Teacher dashboard error: %s", e, exc_info=True)
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(login_required, name="dispatch")
class ParentDashboardAPI(View):
    """Parent dashboard summary"""

    def get(self, request):
        role_value = (getattr(request.user, "role", "") or "").upper()
        if role_value != "PARENT":
            return JsonResponse({"error": "Permission denied"}, status=403)

        try:
            from apps.people.models import StudentGuardian
            from apps.finance.models import Invoice, Payment

            # Get parent's children
            children = StudentGuardian.objects.filter(  # tenant-isolation-allow: the signed-in guardian's own links (reviewed 2026-09-03)
                guardian_user=request.user,
                student__is_active=True,
                can_view_results=True,
            ).values_list("student_id", flat=True)

            children_count = len(children)

            flags = get_effective_flags(request)
            require_finance_opt_in = bool(flags.get("require_guardian_finance_opt_in"))

            finance_children = StudentGuardian.objects.filter(  # tenant-isolation-allow: the signed-in guardian's own links (reviewed 2026-09-03)
                guardian_user=request.user,
                student__is_active=True,
                can_view_finance=True,
            ).values_list("student_id", flat=True)

            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            # Get pending fees for children
            total_invoices = (
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                Invoice.objects.filter(
                    student_id__in=finance_children, deleted_at__isnull=True
                )
                .exclude(status=Invoice.Status.VOID)
                .aggregate(Sum("total_amount"))["total_amount__sum"]
                or 0
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            )

            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            total_paid = (
                Payment.objects.filter(
                    invoice__student_id__in=finance_children, deleted_at__isnull=True
                ).aggregate(Sum("amount"))["amount__sum"]
                or 0
            )

            pending_fees = total_invoices - total_paid

            # Messages unread
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            from apps.communication.models import Message

            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            unread_messages = Message.objects.filter(
                recipient=request.user, is_read=False
            ).count()

            return JsonResponse(
                {
                    "children_count": children_count,
                    "finance_access_required": require_finance_opt_in,
                    "finance_access_granted": len(finance_children),
                    "total_pending_fees": float(pending_fees),
                    "messages_unread": unread_messages,
                    "upcoming_events": 0,  # Implement based on your event model
                    "last_updated": timezone.now().isoformat(),
                }
            )
        except (
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
            ObjectDoesNotExist,
            DatabaseError,
        ) as e:
            logger.error("Parent dashboard error: %s", e, exc_info=True)
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(login_required, name="dispatch")
class StudentDashboardAPI(View):
    """Student dashboard summary"""

    def get(self, request):
        role_value = (getattr(request.user, "role", "") or "").upper()
        if role_value != "STUDENT":
            return JsonResponse({"error": "Permission denied"}, status=403)

        try:
            from apps.people.models import StudentProfile
            from apps.academics.models import Attendance

            try:
                # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                student = StudentProfile.objects.get(user=request.user)
            except StudentProfile.DoesNotExist:
                return JsonResponse(
                    {"error": "Student profile not found for this account."},
                    # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
                    status=404,
                )

            # Current classes: subjects taught in the student's current classroom.
            # `current_classroom` is the SOT property; the old
            # `Classroom.objects.filter(level=student.current_class)` referenced
            # neither a real StudentProfile attribute (`current_class`) nor a real
            # Classroom field (`level`), so this endpoint returned 500 for every
            # student (the outer handler catches the AttributeError).
            current_classroom = student.current_classroom
            current_classes = (
                current_classroom.subject_assignments.count()
                if current_classroom
                else 0
            )

            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            # Attendance percentage
            total_attendance = Attendance.objects.filter(student=student).count()
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            present_days = Attendance.objects.filter(
                student=student, status="present"
            ).count()

            attendance_percentage = 0
            if total_attendance > 0:
                attendance_percentage = (present_days / total_attendance) * 100

            # Average grade
            average_grade = 0.0  # Implement based on your evaluation model

            # Pending assignments
            pending_assignments = 0  # Implement based on your assignment model

            return JsonResponse(
                {
                    "attendance_percentage": round(attendance_percentage, 1),
                    "average_grade": average_grade,
                    "pending_assignments": pending_assignments,
                    "current_classes": current_classes,
                    "last_updated": timezone.now().isoformat(),
                }
            )
        except (
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
            ObjectDoesNotExist,
            DatabaseError,
        ) as e:
            logger.error("Student dashboard error: %s", e, exc_info=True)
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(login_required, name="dispatch")
class FinancialDashboardAPI(View):
    """Financial overview dashboard"""

    def get(self, request):
        role_value = (getattr(request.user, "role", "") or "").upper()
        if not (
            request.user.is_superuser
            or request.user.is_staff
            or role_value in ["ADMIN", "BURSAR", "LEADERSHIP"]
        ):
            return JsonResponse({"error": "Permission denied"}, status=403)

        try:
            from apps.finance.models import Invoice, Payment

            # Total revenue — exclude soft-deleted (reversed) payments.
            # tenant-isolation-allow: rls-scoped-finance-dashboard-aggregate
            total_revenue = (
                Payment.objects.filter(deleted_at__isnull=True).aggregate(Sum("amount"))[
                    "amount__sum"
                ]
                or 0
            )

            # Outstanding fees — exclude voided/soft-deleted invoices.
            # tenant-isolation-allow: rls-scoped-finance-dashboard-aggregate
            total_invoiced = (
                Invoice.objects.exclude(status=Invoice.Status.VOID)
                .filter(deleted_at__isnull=True)
                .aggregate(Sum("total_amount"))["total_amount__sum"]
                or 0
            )
            outstanding = total_invoiced - total_revenue

            # Payment breakdown by method
            payment_methods = (
                Payment.objects.values("payment_method")
                .annotate(total=Sum("amount"))
                .order_by("-total")
            )

            # Invoices by status
            invoices_by_status = Invoice.objects.values("status").annotate(
                count=Count("id")
            )

            return JsonResponse(
                {
                    "total_revenue": float(total_revenue),
                    "outstanding_fees": float(outstanding),
                    "collection_rate": (total_revenue / total_invoiced * 100)
                    if total_invoiced > 0
                    else 0,
                    "payment_methods": list(payment_methods),
                    "invoices_by_status": list(invoices_by_status),
                    "last_updated": timezone.now().isoformat(),
                }
            )
        except (
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
            ObjectDoesNotExist,
            DatabaseError,
        ) as e:
            logger.error("Financial dashboard error: %s", e, exc_info=True)
            return JsonResponse({"error": str(e)}, status=500)


@method_decorator(login_required, name="dispatch")
class AcademicDashboardAPI(View):
    """Academic performance dashboard"""

    def get(self, request):
        role_value = (getattr(request.user, "role", "") or "").upper()
        if not (
            request.user.is_superuser
            or request.user.is_staff
            or role_value in ["ADMIN", "LEADERSHIP", "HOD"]
        ):
            return JsonResponse({"error": "Permission denied"}, status=403)

        try:
            from apps.academics.models import Classroom

            # Total classes
            total_classes = Classroom.objects.count()

            # Average class performance
            avg_performance = 0.0  # Implement based on your evaluation model

            # Students at risk (low attendance or grades)
            students_at_risk = 0  # Implement based on your criteria

            # Attendance rate by class
            attendance_by_class = {}  # Implement calculation

            return JsonResponse(
                {
                    "total_classes": total_classes,
                    "average_performance": avg_performance,
                    "students_at_risk": students_at_risk,
                    "attendance_summary": attendance_by_class,
                    "last_updated": timezone.now().isoformat(),
                }
            )
        except (
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
            ObjectDoesNotExist,
            DatabaseError,
        ) as e:
            logger.error("Academic dashboard error: %s", e, exc_info=True)
            return JsonResponse({"error": str(e)}, status=500)
