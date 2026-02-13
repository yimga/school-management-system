"""Entity CRUD and session-claims APIs for frontend orchestration."""
from django.db import transaction
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Specialty
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.evals.models import TeacherAssignment
from apps.siteconfig.models import SiteSettings

from .serializers import (
    ClassroomSerializer,
    StudentGuardianSerializer,
    StudentProfileSerializer,
    TeacherProfileSerializer,
    UserSerializer,
)


ADMIN_ROLES = {
    "ADMIN",
    "LEADERSHIP",
    "PRINCIPAL",
    "VICE_PRINCIPAL",
    "DEAN",
    "IT_ADMIN",
    "CENSOR",
    "BURSAR",
}


def _is_admin_like(user: User) -> bool:
    role = (getattr(user, "role", "") or "").upper()
    return bool(user.is_staff or user.is_superuser or role in ADMIN_ROLES)


def _backend_flags() -> dict:
    site = SiteSettings.get_solo()
    return getattr(site, "backend_feature_flags", {}) or {}


def _check_student_offline_conflict(instance, request):
    """If X-Client-Updated-At is present, compare with instance.updated_at; return 409 Response if client is older."""
    raw = request.headers.get("X-Client-Updated-At") or request.META.get("HTTP_X_CLIENT_UPDATED_AT")
    if not raw or not str(raw).strip():
        return None
    client_dt = parse_datetime(str(raw).strip())
    if client_dt is None:
        return None
    if timezone.is_naive(client_dt):
        client_dt = timezone.make_aware(client_dt)
    server_dt = getattr(instance, "updated_at", None)
    if server_dt is None:
        return None
    if timezone.is_naive(server_dt):
        server_dt = timezone.make_aware(server_dt)
    if client_dt < server_dt:
        return Response(
            {"error": "conflict", "server_updated_at": server_dt.isoformat()},
            status=status.HTTP_409_CONFLICT,
        )
    return None


class StudentProfileViewSet(viewsets.ModelViewSet):
    """CRUD for student profiles; scoped by role."""

    serializer_class = StudentProfileSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        user = self.request.user
        role = (getattr(user, "role", "") or "").upper()
        base = StudentProfile.objects.select_related("academic_year", "classroom", "specialty")
        school = getattr(self.request, "school", None)
        if school is not None:
            base = base.filter(school=school)

        if _is_admin_like(user):
            return base

        if role == "TEACHER":
            from apps.evals.models import TeacherAssignment

            teacher = getattr(user, "teacher_profile", None)
            if not teacher:
                return base.none()
            classroom_ids = TeacherAssignment.objects.filter(
                teacher=teacher, is_active=True
            ).values_list("subject_assignment__classroom_id", flat=True)
            return base.filter(classroom_id__in=classroom_ids)

        if role == "PARENT":
            child_ids = StudentGuardian.objects.filter(
                guardian_user=user, can_view_results=True
            ).values_list("student_id", flat=True)
            return base.filter(id__in=child_ids)

        # Students without linked profile fallback to empty to avoid leakage.
        return base.none()

    # --- Writes restricted to admin-like users ---
    def _require_admin(self, request):
        if not _is_admin_like(request.user):
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        return None

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def update(self, request, *args, **kwargs):
        partial = kwargs.get("partial", False)
        instance = self.get_object()
        denied = self._require_admin(request)
        if denied:
            return denied
        conflict = _check_student_offline_conflict(instance, request)
        if conflict:
            return conflict
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="bulk-assign")
    def bulk_assign(self, request):
        """Assign multiple students to a classroom/specialty/academic year in one call."""
        denied = self._require_admin(request)
        if denied:
            return denied

        student_ids = request.data.get("student_ids") or []
        classroom_id = request.data.get("classroom")
        specialty_id = request.data.get("specialty")
        academic_year_id = request.data.get("academic_year")

        if not student_ids or not isinstance(student_ids, (list, tuple)):
            return Response({"error": "student_ids must be a non-empty list"}, status=status.HTTP_400_BAD_REQUEST)

        updates = {}
        for field_name, model, value in (
            ("classroom_id", Classroom, classroom_id),
            ("specialty_id", Specialty, specialty_id),
            ("academic_year_id", AcademicYear, academic_year_id),
        ):
            if value:
                if not model.objects.filter(id=value).exists():
                    return Response({"error": f"{model.__name__} not found"}, status=status.HTTP_404_NOT_FOUND)
                updates[field_name] = value

        if not updates:
            return Response({"error": "At least one of classroom, specialty, academic_year is required"}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            updated = StudentProfile.objects.filter(id__in=student_ids).update(**updates, updated_by=request.user)

        return Response({"updated": updated, "applied": updates}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="bulk-preview")
    def bulk_preview(self, request):
        """Parse a CSV payload for student import and return a dry-run preview."""
        denied = self._require_admin(request)
        if denied:
            return denied
        flags = _backend_flags()
        max_rows = int(flags.get("max_bulk_import_rows", 500))

        csv_text = request.data.get("csv")
        if not csv_text:
            return Response({"error": "csv body is required"}, status=status.HTTP_400_BAD_REQUEST)

        reader = csv.DictReader(io.StringIO(csv_text))
        preview = []
        errors = []
        for idx, row in enumerate(reader, start=1):
            if max_rows and idx > max_rows:
                errors.append({"row": idx, "error": f"Row limit exceeded ({max_rows})"})
                break
            record = {
                "first_name": row.get("first_name", "").strip(),
                "last_name": row.get("last_name", "").strip(),
                "admission_number": row.get("admission_number", "").strip(),
                "academic_year": row.get("academic_year"),
                "classroom": row.get("classroom"),
                "specialty": row.get("specialty"),
                "status": row.get("status", "NEW"),
            }
            missing = [k for k in ("first_name", "last_name") if not record[k]]
            if missing:
                errors.append({"row": idx, "error": f"Missing required fields: {', '.join(missing)}"})
            preview.append(record)

        return Response({"preview": preview, "errors": errors}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="bulk-commit")
    def bulk_commit(self, request):
        """Create student records from a parsed payload (admin-only)."""
        denied = self._require_admin(request)
        if denied:
            return denied
        flags = _backend_flags()
        if not flags.get("allow_bulk_commit", True):
            return Response({"error": "Bulk commit disabled by admin."}, status=status.HTTP_403_FORBIDDEN)
        max_rows = int(flags.get("max_bulk_import_rows", 500))

        rows = request.data.get("rows") or []
        if not isinstance(rows, list) or not rows:
            return Response({"error": "rows must be a non-empty list"}, status=status.HTTP_400_BAD_REQUEST)

        if max_rows and len(rows) > max_rows:
            return Response({"error": f"rows exceeds max_bulk_import_rows ({max_rows})"}, status=status.HTTP_400_BAD_REQUEST)

        created = []
        errors = []
        for idx, row in enumerate(rows, start=1):
            try:
                serializer = self.get_serializer(data=row)
                serializer.is_valid(raise_exception=True)
                obj = serializer.save(created_by=request.user, updated_by=request.user)
                created.append(obj.id)
            except Exception as exc:  # noqa: BLE001
                errors.append({"row": idx, "error": str(exc)})

        return Response({"created": created, "errors": errors}, status=status.HTTP_201_CREATED)


class TeacherProfileViewSet(viewsets.ModelViewSet):
    """CRUD for teachers; admin-only writes, teacher self-read."""

    serializer_class = TeacherProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role = (getattr(user, "role", "") or "").upper()
        base = TeacherProfile.objects.select_related("user", "department", "reports_to")
        school = getattr(self.request, "school", None)
        if school is not None:
            base = base.filter(school=school)

        if _is_admin_like(user):
            return base

        if role == "TEACHER":
            profile = getattr(user, "teacher_profile", None)
            if profile:
                return base.filter(id=profile.id)

        return base.none()

    def _require_admin(self, request):
        if not _is_admin_like(request.user):
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        return None


class StudentGuardianViewSet(viewsets.ModelViewSet):
    """Manage guardian/student links; parents can view their own links, admins manage all."""

    serializer_class = StudentGuardianSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        base = StudentGuardian.objects.select_related("guardian_user", "student")
        school = getattr(self.request, "school", None)
        if school is not None and hasattr(StudentGuardian, "school"):
            base = base.filter(school=school)
        elif school is not None:
            base = base.filter(student__school=school)
        if _is_admin_like(user):
            return base
        return base.filter(guardian_user=user)

    def create(self, request, *args, **kwargs):
        # Parents can only create links for themselves; admins can create for anyone.
        if not _is_admin_like(request.user):
            guardian_id = request.data.get("guardian_user")
            if guardian_id and str(guardian_id) != str(request.user.id):
                return Response({"error": "You can only link yourself as guardian."}, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not _is_admin_like(request.user):
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not _is_admin_like(request.user):
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not _is_admin_like(request.user):
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="bulk-preview")
    def bulk_preview(self, request):
        """Dry-run parse of guardian CSV data."""
        if not _is_admin_like(request.user):
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        flags = _backend_flags()
        max_rows = int(flags.get("max_bulk_import_rows", 500))

        csv_text = request.data.get("csv")
        if not csv_text:
            return Response({"error": "csv body is required"}, status=status.HTTP_400_BAD_REQUEST)

        reader = csv.DictReader(io.StringIO(csv_text))
        preview = []
        errors = []
        for idx, row in enumerate(reader, start=1):
            if max_rows and idx > max_rows:
                errors.append({"row": idx, "error": f"Row limit exceeded ({max_rows})"})
                break
            record = {
                "guardian_user": row.get("guardian_user"),
                "student": row.get("student"),
                "relationship": row.get("relationship", "GUARDIAN"),
                "can_view_results": row.get("can_view_results", "true"),
                "can_view_finance": row.get("can_view_finance", "false"),
            }
            if not record["guardian_user"] or not record["student"]:
                errors.append({"row": idx, "error": "guardian_user and student are required"})
            preview.append(record)

        return Response({"preview": preview, "errors": errors}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="bulk-commit")
    def bulk_commit(self, request):
        """Create guardian links from parsed payload (admin-only)."""
        if not _is_admin_like(request.user):
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        flags = _backend_flags()
        if not flags.get("allow_bulk_commit", True):
            return Response({"error": "Bulk commit disabled by admin."}, status=status.HTTP_403_FORBIDDEN)
        max_rows = int(flags.get("max_bulk_import_rows", 500))

        rows = request.data.get("rows") or []
        if not isinstance(rows, list) or not rows:
            return Response({"error": "rows must be a non-empty list"}, status=status.HTTP_400_BAD_REQUEST)
        if max_rows and len(rows) > max_rows:
            return Response({"error": f"rows exceeds max_bulk_import_rows ({max_rows})"}, status=status.HTTP_400_BAD_REQUEST)

        created = []
        errors = []
        for idx, row in enumerate(rows, start=1):
            try:
                serializer = self.get_serializer(data=row)
                serializer.is_valid(raise_exception=True)
                obj = serializer.save()
                created.append(obj.id)
            except Exception as exc:  # noqa: BLE001
                errors.append({"row": idx, "error": str(exc)})

        return Response({"created": created, "errors": errors}, status=status.HTTP_201_CREATED)


class ClassroomViewSet(viewsets.ModelViewSet):
    """Classroom CRUD; open read, admin-only writes."""

    serializer_class = ClassroomSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        qs = Classroom.objects.select_related("academic_year", "department")
        school = getattr(self.request, "school", None)
        if school is not None:
            qs = qs.filter(school=school)
        return qs

    def _require_admin(self, request):
        if not _is_admin_like(request.user):
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        return None


class SessionClaimsView(APIView):
    """Return JWT-like claims for the current session to drive frontend RBAC."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        role = (getattr(user, "role", "") or "").upper()
        roles = list(user.roles.values_list("code", flat=True))
        feature_permissions = list(user.feature_permissions.values_list("code", flat=True))

        payload = {
            "user": UserSerializer(user, context={"request": request}).data,
            "role": role,
            "roles": roles,
            "feature_permissions": feature_permissions,
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
        }
        school = getattr(request, "school", None)
        if school is not None:
            payload["school_id"] = str(school.id)
        return Response(payload)


class ProfileView(APIView):
    """Current user profile for mobile/frontend. GET /api/auth/profile/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = UserSerializer(request.user, context={"request": request}).data
        role = (getattr(request.user, "role", "") or "").upper()
        data["role"] = role
        return Response(data)


class TeacherRosterView(APIView):
    """Roster aggregation for teachers/admins to drive course/quiz builders."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        role = (getattr(user, "role", "") or "").upper()
        admin_like = _is_admin_like(user)
        teacher_profile = getattr(user, "teacher_profile", None)

        if not admin_like and role != "TEACHER":
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)

        teacher_ids = [teacher_profile.id] if teacher_profile and not admin_like else None

        assignments = TeacherAssignment.objects.filter(is_active=True)
        school = getattr(request, "school", None)
        if school is not None:
            assignments = assignments.filter(school=school)
        if teacher_ids:
            assignments = assignments.filter(teacher_id__in=teacher_ids)

        rosters = []
        for assignment in assignments.select_related(
            "teacher__user",
            "subject_assignment__classroom",
            "subject_assignment__specialty",
        ).distinct():
            classroom = assignment.subject_assignment.classroom
            specialty = assignment.subject_assignment.specialty
            students_qs = StudentProfile.objects.filter(
                classroom=classroom,
                specialty=specialty,
                is_active=True,
            )
            if school is not None:
                students_qs = students_qs.filter(school=school)
            students = students_qs.values("id", "first_name", "last_name", "student_code")
            rosters.append({
                "classroom": classroom.name if classroom else None,
                "classroom_id": getattr(classroom, "id", None),
                "specialty": specialty.name if specialty else None,
                "specialty_id": getattr(specialty, "id", None),
                "teacher": getattr(assignment.teacher, "id", None),
                "teacher_name": getattr(getattr(assignment.teacher, "user", None), "get_full_name", lambda: None)(),
                "students": list(students),
            })

        return Response({"rosters": rosters})
import csv
import io
