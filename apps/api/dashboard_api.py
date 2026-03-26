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
            total_students = StudentProfile.objects.filter(is_active=True).count()
            total_teachers = TeacherProfile.objects.filter(is_active=True).count()
            total_parents = 0  # Implement based on your parent model

            # Finance data
            total_invoices = (
                Invoice.objects.aggregate(Sum("total_amount"))["total_amount__sum"] or 0
            )
            total_paid = Payment.objects.aggregate(Sum("amount"))["amount__sum"] or 0
            pending_fees = total_invoices - total_paid

            # Attendance
            today = timezone.now().date()
            attendance_today = Attendance.objects.filter(
                date=today, status="present"
            ).count()
            attendance_rate = 0
            if total_students > 0:
                attendance_rate = (attendance_today / total_students) * 100

            # Active users today
            from django.contrib.auth.models import User

            last_24h = timezone.now() - timedelta(hours=24)
            active_users = User.objects.filter(last_login__gte=last_24h).count()

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
                teacher = TeacherProfile.objects.get(user=request.user)
            except TeacherProfile.DoesNotExist:
                return JsonResponse(
                    {"error": "Teacher profile not found for this account."},
                    status=404,
                )

            active_year, _active_term = get_active_year_and_term()
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
                    student_filters &= Q(academic_year=active_year)
                my_students = (
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
            children = StudentGuardian.objects.filter(
                guardian_user=request.user,
                student__is_active=True,
                can_view_results=True,
            ).values_list("student_id", flat=True)

            children_count = len(children)

            flags = get_effective_flags(request)
            require_finance_opt_in = bool(flags.get("require_guardian_finance_opt_in"))

            finance_children = StudentGuardian.objects.filter(
                guardian_user=request.user,
                student__is_active=True,
                can_view_finance=True,
            ).values_list("student_id", flat=True)

            # Get pending fees for children
            total_invoices = (
                Invoice.objects.filter(student_id__in=finance_children).aggregate(
                    Sum("total_amount")
                )["total_amount__sum"]
                or 0
            )

            total_paid = (
                Payment.objects.filter(
                    invoice__student_id__in=finance_children
                ).aggregate(Sum("amount"))["amount__sum"]
                or 0
            )

            pending_fees = total_invoices - total_paid

            # Messages unread
            from apps.communication.models import Message

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
            from apps.academics.models import Attendance, Classroom

            try:
                student = StudentProfile.objects.get(user=request.user)
            except StudentProfile.DoesNotExist:
                return JsonResponse(
                    {"error": "Student profile not found for this account."},
                    status=404,
                )

            # Current classes
            current_classes = Classroom.objects.filter(
                level=student.current_class
            ).count()

            # Attendance percentage
            total_attendance = Attendance.objects.filter(student=student).count()
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

            # Total revenue
            total_revenue = Payment.objects.aggregate(Sum("amount"))["amount__sum"] or 0

            # Outstanding fees
            total_invoiced = (
                Invoice.objects.aggregate(Sum("total_amount"))["total_amount__sum"] or 0
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
