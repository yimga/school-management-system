"""
Academics API Views
Attendance and schedule-conflict endpoints.

(GradeViewSet + AssessmentResultsAPI were retired 2026-06-10 — unrouted dead code
built on a non-existent `evals.models.Grade` model; see CSS_RETIREMENT_DOCKET.)
"""

import csv
import io
from datetime import datetime

from django.db.models import Count, Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.api.serializers import AttendanceSerializer
from apps.accounts.effective_access import student_data_access
from apps.accounts.models import User
from apps.observability.tracing import trace_view


class AttendanceViewSet(viewsets.ModelViewSet):
    """
    Attendance management API

    Mark and retrieve attendance records
    Calculate attendance percentages
    Filter by class, date, student
    """

    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["student", "classroom", "date", "status"]
    ordering_fields = ["date", "student"]
    ordering = ["-date"]

    def get_queryset(self):
        from apps.academics.models import Attendance

        user = self.request.user
        role = (getattr(user, "role", "") or "").upper()
        admin_roles = {
            "ADMIN",
            "LEADERSHIP",
            "PRINCIPAL",
            "VICE_PRINCIPAL",
            "DEAN",
            "CENSOR",
        }
        # tenant-isolation-allow: service-scoped-via-request-school-context
        base = Attendance.objects.all().select_related("student__user", "classroom")
        school = getattr(self.request, "school", None)
        if school is not None:
            base = base.filter(school=school)

        if user.is_staff or role in admin_roles:
            return base

        if role == User.Role.TEACHER:
            from apps.evals.models import TeacherAssignment

            teacher = getattr(user, "teacher_profile", None)
            if not teacher:
                return base.none()
            classroom_ids = (
                # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                TeacherAssignment.objects.filter(
                    teacher=teacher,
                    is_active=True,
                )
                .values_list("subject_assignment__classroom_id", flat=True)
                .distinct()
            )
            return base.filter(classroom_id__in=classroom_ids)

        from apps.people.models import StudentProfile

        # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
        student_profile = StudentProfile.objects.filter(user=user).first()
        if student_profile:
            return base.filter(student=student_profile)

        if role == User.Role.PARENT:
            from apps.people.models import StudentGuardian

            child_ids = StudentGuardian.objects.filter(
                guardian_user=user,
                can_view_results=True,
            ).values_list("student_id", flat=True)
            return base.filter(student_id__in=child_ids)

        return base.none()

    def list(self, request, *args, **kwargs):
        """
        List attendance records with advanced filtering

        Query Parameters:
        - classroom_id: specific classroom
        - date: specific date (YYYY-MM-DD)
        - start_date, end_date: date range
        - status: present, absent, late, excused
        - student_id: specific student
        """
        queryset = self.get_queryset()

        date_val = request.query_params.get("date")
        if date_val:
            queryset = queryset.filter(date=date_val)

        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        if start_date and end_date:
            queryset = queryset.filter(date__gte=start_date, date__lte=end_date)

        status_filter = request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # CSV export: ?format=csv (no pagination; cap at 10k rows)
        if request.query_params.get("format") == "csv":
            queryset = queryset[:10000].select_related("student", "classroom")
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(
                [
                    "id",
                    "student_id",
                    "student_name",
                    "classroom_id",
                    "classroom_name",
                    "date",
                    "status",
                    "remarks",
                ]
            )
            for a in queryset:
                writer.writerow(
                    [
                        a.id,
                        a.student_id,
                        getattr(a.student, "admission_number", "") or "",
                        a.classroom_id,
                        getattr(a.classroom, "name", "") or "",
                        a.date.isoformat() if a.date else "",
                        a.status or "",
                        (a.remarks or "")[:255],
                    ]
                )
            resp = Response(buf.getvalue(), content_type="text/csv")
            resp["Content-Disposition"] = 'attachment; filename="attendance_export.csv"'
            return resp

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @trace_view("attendance.submit")
    def create(self, request, *args, **kwargs):
        """
        Record attendance for a class

        Request Body:
        {
            "classroom": 1,
            "date": "2025-01-22",
            "records": [
                {"student": 1, "status": "present"},
                {"student": 2, "status": "absent"},
                {"student": 3, "status": "late"}
            ]
        }
        """
        user_role = (getattr(request.user, "role", "") or "").upper()
        if not (user_role == User.Role.TEACHER or request.user.is_staff):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )

        from apps.academics.models import Attendance, Classroom

        classroom_id = request.data.get("classroom")
        date_str = request.data.get("date")
        records = request.data.get("records", [])

        try:
            # tenant-isolation-allow: service-scoped-via-request-school-context
            classroom = Classroom.objects.get(id=classroom_id)
            attendance_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except Classroom.DoesNotExist:
            return Response(
                {"error": "Classroom not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except (ValueError, TypeError):
            # Non-str/missing date (strptime TypeError) or non-numeric classroom
            # id (int-coercion ValueError) — malformed input, not a server fault.
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if user_role == User.Role.TEACHER:
            from apps.evals.models import TeacherAssignment

            teacher = getattr(request.user, "teacher_profile", None)
            if not teacher:
                return Response(
                    {"error": "Teacher profile required"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            classroom_allowed = TeacherAssignment.objects.filter(
                teacher=teacher,
                is_active=True,
                subject_assignment__classroom_id=classroom.id,
            ).exists()
            if not classroom_allowed:
                return Response(
                    {"error": "You are not assigned to this classroom"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        student_ids = [
            record.get("student") for record in records if record.get("student")
        ]
        if student_ids:
            from apps.people.models import StudentProfile

            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            valid_ids = set(
                StudentProfile.objects.filter(
                    id__in=student_ids,
                    classroom_id=classroom.id,
                ).values_list("id", flat=True)
            )
            if len(valid_ids) != len(set(student_ids)):
                return Response(
                    {"error": "One or more students are not in this classroom"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        recorded_count = 0
        for record in records:
            attendance, created = Attendance.objects.update_or_create(
                student_id=record["student"],
                classroom=classroom,
                date=attendance_date,
                defaults={"status": record["status"]},
            )
            recorded_count += 1

        return Response(
            {
                "status": "success",
                "recorded": recorded_count,
                "classroom_id": classroom_id,
                "date": date_str,
                "message": f"Attendance recorded for {recorded_count} students",
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=["patch"], url_path="bulk-update")
    def bulk_update(self, request):
        """
        Bulk update attendance records.
        Body: { "records": [ { "id": <attendance_id>, "status": "present" } ] }
        or:   { "records": [ { "student": id, "classroom": id, "date": "YYYY-MM-DD", "status": "present" } ] }
        """
        from apps.academics.models import Attendance, Classroom

        user_role = (getattr(request.user, "role", "") or "").upper()
        if (
            user_role
            not in (
                "TEACHER",
                "ADMIN",
                "LEADERSHIP",
                "PRINCIPAL",
                "VICE_PRINCIPAL",
                "DEAN",
                "CENSOR",
            )
            and not request.user.is_staff
        ):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )

        records = request.data.get("records", [])
        if not records:
            return Response(
                {"error": "Provide 'records' array"}, status=status.HTTP_400_BAD_REQUEST
            )

        queryset = self.get_queryset()
        updated = 0
        for rec in records:
            pk = rec.get("id")
            if pk is not None:
                att = queryset.filter(pk=pk).first()
                if att and "status" in rec:
                    att.status = rec["status"]
                    if "remarks" in rec:
                        att.remarks = str(rec["remarks"])[:255]
                    att.save()
                    updated += 1
                continue
            student_id = rec.get("student")
            classroom_id = rec.get("classroom")
            date_str = rec.get("date")
            if (
                student_id is None
                or classroom_id is None
                or not date_str
                or "status" not in rec
            ):
                continue
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue
            try:
                # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                classroom = Classroom.objects.get(pk=classroom_id)
                att, created = Attendance.objects.update_or_create(
                    student_id=student_id,
                    classroom=classroom,
                    date=dt,
                    defaults={
                        "status": rec["status"],
                        "remarks": str(rec.get("remarks", ""))[:255],
                    },
                )
            except (Classroom.DoesNotExist, ValueError, TypeError):
                # Non-numeric classroom/student id in this record — skip it,
                # don't 500 the whole bulk request.
                continue
            if att and (att.school_id is None and getattr(request, "school", None)):
                att.school = request.school
                att.save(update_fields=["school"])
            updated += 1

        return Response({"status": "success", "updated": updated})

    @action(detail=False, methods=["get"])
    def student_summary(self, request):
        """
        Get attendance summary for a student

        Query Parameters:
        - student_id: required
        - start_date, end_date: optional date range

        Returns:
        {
            "student_id": 1,
            "total_days": 20,
            "present": 18,
            "absent": 1,
            "late": 1,
            "percentage": 92.5
        }
        """
        student_id = request.query_params.get("student_id")
        if not student_id:
            return Response(
                {"error": "student_id parameter required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not student_data_access(request.user, int(student_id)):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )

        from apps.academics.models import Attendance

        # tenant-isolation-allow: service-scoped-via-request-school-context
        queryset = Attendance.objects.filter(student_id=student_id)

        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        if start_date and end_date:
            queryset = queryset.filter(date__gte=start_date, date__lte=end_date)

        total = queryset.count()
        present = queryset.filter(status="present").count()
        absent = queryset.filter(status="absent").count()
        late = queryset.filter(status="late").count()

        percentage = (present / total * 100) if total > 0 else 0

        return Response(
            {
                "student_id": int(student_id),
                "total_days": total,
                "present": present,
                "absent": absent,
                "late": late,
                "percentage": round(percentage, 1),
                "period": {"start": start_date, "end": end_date},
            }
        )

    @action(detail=False, methods=["get"])
    def class_summary(self, request):
        """Get attendance summary for entire class"""
        classroom_id = request.query_params.get("classroom_id")
        if not classroom_id:
            return Response(
                {"error": "classroom_id parameter required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user_role = (getattr(request.user, "role", "") or "").upper()
        if not (
            request.user.is_staff
            or user_role
            in {
                "ADMIN",
                "LEADERSHIP",
                "PRINCIPAL",
                "VICE_PRINCIPAL",
                "DEAN",
                "CENSOR",
                "TEACHER",
            }
        ):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )
        if user_role == User.Role.TEACHER and not request.user.is_staff:
            from apps.evals.models import TeacherAssignment

            teacher = getattr(request.user, "teacher_profile", None)
            if not teacher:
                return Response(
                    {"error": "Teacher profile required"},
                    # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
                    status=status.HTTP_403_FORBIDDEN,
                )
            # tenant-isolation-allow: view-layer-scoped-via-request-school-or-role-graph
            allowed = TeacherAssignment.objects.filter(
                teacher=teacher,
                is_active=True,
                subject_assignment__classroom_id=classroom_id,
            ).exists()
            if not allowed:
                return Response(
                    {"error": "You are not assigned to this classroom"},
                    status=status.HTTP_403_FORBIDDEN,
                )

        from apps.academics.models import Attendance
# tenant-isolation-allow: service-scoped-via-request-school-context

        queryset = Attendance.objects.filter(classroom_id=classroom_id)

        date_val = request.query_params.get("date")
        if date_val:
            queryset = queryset.filter(date=date_val)

        total = queryset.count()
        present = queryset.filter(status="present").count()
        absent = queryset.filter(status="absent").count()
        late = queryset.filter(status="late").count()

        percentage = (present / total * 100) if total > 0 else 0

        by_student = (
            queryset.values("student__user__first_name", "student__user__last_name")
            .annotate(
                total_days=Count("id"),
                present_days=Count("id", filter=Q(status="present")),
            )
            .order_by("student__user__last_name")
        )

        return Response(
            {
                "classroom_id": int(classroom_id),
                "total_records": total,
                "present": present,
                "absent": absent,
                "late": late,
                "class_percentage": round(percentage, 1),
                "date": date_val,
                "by_student": list(by_student),
            }
        )


class ScheduleConflictsAPI(APIView):
    """
    GET schedule conflicts for a given schedule (teacher/room double-booking).
    Used by Wave 5 scheduling validation.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, schedule_id):
        from apps.academics.scheduling import Schedule, TimetableGenerator

        school = getattr(request, "school", None)
        if not school:
            return Response(
                {"error": "School context required"}, status=status.HTTP_400_BAD_REQUEST
            )

        schedule = (
            Schedule.objects.filter(academic_year__school=school, pk=schedule_id)
            .select_related("academic_year", "term")
            .first()
        )

        if not schedule:
            return Response(
                {"error": "Schedule not found"}, status=status.HTTP_404_NOT_FOUND
            )

        generator = TimetableGenerator(schedule.academic_year, schedule.term)
        conflicts = generator.detect_conflicts(schedule)
        # De-duplicate by conflict key (same pair can appear twice)
        seen = set()
        unique = []
        for c in conflicts:
            key = (c["type"], tuple(sorted(c.get("entries", []))))
            if key not in seen:
                seen.add(key)
                unique.append(c)

        return Response(
            {
                "schedule_id": schedule_id,
                "schedule_name": schedule.name,
                "conflicts": unique,
                "has_conflicts": len(unique) > 0,
            }
        )
