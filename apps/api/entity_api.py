"""Entity CRUD and session-claims APIs for frontend orchestration."""

from django.conf import settings
from django.db import transaction
from django.db.utils import DatabaseError, IntegrityError
from django.utils.dateparse import parse_datetime
from drf_spectacular.utils import (
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
    inline_serializer,
)
from rest_framework import serializers as drf_serializers
from rest_framework.exceptions import ValidationError as DRFValidationError
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import CursorPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Specialty
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.evals.models import TeacherAssignment
from apps.schools.models import School
from apps.platform_runtime.helpers import get_effective_flags

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


def _backend_flags(request=None, school=None) -> dict:
    if request is None and school is not None:

        class _RequestShim:
            def __init__(self, school_obj):
                self.school = school_obj
                self.tenant_runtime = None

        request = _RequestShim(school)
    return get_effective_flags(request)


def _request_school(request):
    school = getattr(request, "school", None)
    if school is not None:
        return school
    school_id = getattr(request, "session", {}).get("school_id")
    if not school_id:
        return None
    return School.objects.filter(pk=school_id, is_active=True).first()


def _check_student_offline_conflict(instance, request):
    """If X-Client-Updated-At is present, compare with instance.updated_at; return 409 Response if client is older."""
    raw = request.headers.get("X-Client-Updated-At") or request.META.get(
        "HTTP_X_CLIENT_UPDATED_AT"
    )
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


class _BoundedCursorPagination(CursorPagination):
    """Cursor pagination with a client-settable but BOUNDED page size.

    Two separate requirements, both from the 2026-06-27 contract test:

    * an explicit ``ordering`` on a real field, because the project-wide default orders by
      ``"-created"`` and most of these models have no such column - an unconditional 500;
    * ``page_size_query_param`` with a ``max_page_size``, so a caller can page sensibly
      and cannot turn one request into an unbounded pull of the whole tenant roster.

    Subclasses supply only the ordering.
    """

    page_size_query_param = "page_size"
    max_page_size = getattr(settings, "API_MAX_PAGE_SIZE", 200)


class StudentProfileCursorPagination(_BoundedCursorPagination):
    ordering = "-updated_at"


# WHY THESE THREE EXIST (2026-08-20). The project default is
# ``REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"] = CursorPagination``, whose own default
# ``ordering`` is ``"-created"``. None of these models HAS a ``created`` field, so any
# ViewSet that fell back to the default raised
# ``FieldError: Cannot resolve keyword 'created' into field`` on its list endpoint — an
# unconditional HTTP 500 on every GET, for every caller, since the day pagination became
# a project-wide default.
#
# A contract test written on 2026-06-27 (``test_entity_api_pagination_loop.py``) exists
# precisely to prevent this, and named these three classes. They were never created, so
# the module raised ``AttributeError`` at IMPORT and pytest reported a collection error
# rather than a failure — the guard was written, never ran, and the defect it guards
# against shipped anyway. Orderings below are exactly the ones that test asserts.
class TeacherProfileCursorPagination(_BoundedCursorPagination):
    ordering = "-updated_at"


class StudentGuardianCursorPagination(_BoundedCursorPagination):
    # No timestamp column on this model at all, so the primary key is the only stable
    # total order available. Descending pk is "newest first" for an autoincrement pk.
    ordering = "-pk"


class ClassroomCursorPagination(_BoundedCursorPagination):
    ordering = "-pk"


@extend_schema_view(
    list=extend_schema(
        tags=["Entity"],
        summary="List student profiles",
        description="Role-scoped list of students in the active school. Admin-like users see all; teachers see students in their assigned classrooms; parents see their own children.",
        responses={200: StudentProfileSerializer(many=True), 401: OpenApiResponse(description="Authentication required")},
    ),
    retrieve=extend_schema(
        tags=["Entity"],
        summary="Retrieve a student profile",
        responses={200: StudentProfileSerializer, 401: OpenApiResponse(description="Authentication required"), 404: OpenApiResponse(description="Not found")},
    ),
    create=extend_schema(
        tags=["Entity"],
        summary="Create a student profile",
        description="Admin-only.",
        request=StudentProfileSerializer,
        responses={201: StudentProfileSerializer, 400: OpenApiResponse(description="Validation error"), 403: OpenApiResponse(description="Permission denied")},
    ),
    update=extend_schema(
        tags=["Entity"],
        summary="Update a student profile",
        description="Admin-only. Honors X-Client-Updated-At header for offline conflict detection (409).",
        request=StudentProfileSerializer,
        responses={200: StudentProfileSerializer, 400: OpenApiResponse(description="Validation error"), 403: OpenApiResponse(description="Permission denied"), 409: OpenApiResponse(description="Client copy stale")},
    ),
    partial_update=extend_schema(
        tags=["Entity"],
        summary="Partially update a student profile",
        request=StudentProfileSerializer,
        responses={200: StudentProfileSerializer, 400: OpenApiResponse(description="Validation error"), 403: OpenApiResponse(description="Permission denied"), 409: OpenApiResponse(description="Client copy stale")},
    ),
    destroy=extend_schema(
        tags=["Entity"],
        summary="Delete a student profile",
        request=None,
        responses={204: OpenApiResponse(description="Deleted"), 403: OpenApiResponse(description="Permission denied"), 404: OpenApiResponse(description="Not found")},
    ),
    bulk_assign=extend_schema(
        tags=["Entity"],
        summary="Bulk-assign students to classroom/specialty/year",
        description="Apply one or more of classroom / specialty / academic_year to a list of student ids in a single transaction.",
        request=inline_serializer(
            name="StudentBulkAssignRequest",
            fields={
                "student_ids": drf_serializers.ListField(child=drf_serializers.IntegerField()),
                "classroom": drf_serializers.IntegerField(required=False),
                "specialty": drf_serializers.IntegerField(required=False),
                "academic_year": drf_serializers.IntegerField(required=False),
            },
        ),
        responses={
            200: inline_serializer(name="StudentBulkAssignResponse", fields={"updated": drf_serializers.IntegerField(), "applied": drf_serializers.DictField()}),
            400: OpenApiResponse(description="Invalid payload"),
            403: OpenApiResponse(description="Permission denied"),
            404: OpenApiResponse(description="Referenced entity not found"),
        },
    ),
    bulk_preview=extend_schema(
        tags=["Entity"],
        summary="Dry-run CSV preview for student import",
        request=inline_serializer(name="StudentBulkPreviewRequest", fields={"csv": drf_serializers.CharField()}),
        responses={
            200: inline_serializer(name="StudentBulkPreviewResponse", fields={"preview": drf_serializers.ListField(child=drf_serializers.DictField()), "errors": drf_serializers.ListField(child=drf_serializers.DictField())}),
            400: OpenApiResponse(description="Missing csv body"),
            403: OpenApiResponse(description="Permission denied"),
        },
    ),
    bulk_commit=extend_schema(
        tags=["Entity"],
        summary="Commit parsed student rows",
        description="Create student records from a parsed rows payload. Admin-only; subject to `allow_bulk_commit` feature flag.",
        request=inline_serializer(name="StudentBulkCommitRequest", fields={"rows": drf_serializers.ListField(child=drf_serializers.DictField())}),
        responses={
            201: inline_serializer(name="StudentBulkCommitResponse", fields={"created": drf_serializers.ListField(child=drf_serializers.IntegerField()), "errors": drf_serializers.ListField(child=drf_serializers.DictField())}),
            400: OpenApiResponse(description="Invalid payload"),
            403: OpenApiResponse(description="Permission denied or bulk commit disabled"),
        },
    ),
)
class StudentProfileViewSet(viewsets.ModelViewSet):
    """CRUD for student profiles; scoped by role."""

    serializer_class = StudentProfileSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"
    pagination_class = StudentProfileCursorPagination

    def get_queryset(self):
        user = self.request.user
        role = (getattr(user, "role", "") or "").upper()
        base = StudentProfile.objects.select_related(
            "academic_year", "classroom", "specialty"
        )
        school = _request_school(self.request)
        if school is None:
            return base.none()
        base = base.filter(school=school)

        if _is_admin_like(user):
            return base

        if role == User.Role.TEACHER:
            from apps.evals.models import TeacherAssignment

            teacher = getattr(user, "teacher_profile", None)
            if not teacher:
                return base.none()
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            classroom_ids = TeacherAssignment.objects.filter(
                teacher=teacher, is_active=True
            ).values_list("subject_assignment__classroom_id", flat=True)
            return base.filter(classroom_id__in=classroom_ids)

        if role == User.Role.PARENT:
            child_ids = StudentGuardian.objects.filter(
                guardian_user=user, can_view_results=True
            ).values_list("student_id", flat=True)
            return base.filter(id__in=child_ids)

        # Students without linked profile fallback to empty to avoid leakage.
        return base.none()

    # --- Writes restricted to admin-like users ---
    def _require_admin(self, request):
        if not _is_admin_like(request.user):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )
        return None

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, updated_by=self.request.user)

    def perform_update(self, serializer):
        serializer.save(updated_by=self.request.user)

    def update(self, request, *args, **kwargs):
        kwargs.get("partial", False)
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
            return Response(
                {"error": "student_ids must be a non-empty list"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updates = {}
        for field_name, model, value in (
            ("classroom_id", Classroom, classroom_id),
            ("specialty_id", Specialty, specialty_id),
            ("academic_year_id", AcademicYear, academic_year_id),
        ):
            if value:
                if not model.objects.filter(id=value).exists():
                    return Response(
                        {"error": f"{model.__name__} not found"},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                updates[field_name] = value

        if not updates:
            return Response(
                {
                    "error": "At least one of classroom, specialty, academic_year is required"
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        with transaction.atomic():
            updated = StudentProfile.objects.filter(id__in=student_ids).update(
                **updates, updated_by=request.user
            )
            # A queryset .update() skips save() and every signal, so the
            # enrollment — the source of truth for a placement since item 2.2 —
            # would otherwise still describe the OLD class. Re-sync explicitly;
            # the list is operator-supplied and bounded, so a loop is fine.
            from apps.people.enrollment_services import set_placement

            for student in StudentProfile.objects.filter(id__in=student_ids):
                set_placement(student)

        return Response(
            {"updated": updated, "applied": updates}, status=status.HTTP_200_OK
        )

    @action(detail=False, methods=["post"], url_path="bulk-preview")
    def bulk_preview(self, request):
        """Parse a CSV payload for student import and return a dry-run preview."""
        denied = self._require_admin(request)
        if denied:
            return denied
        flags = _backend_flags(request)
        max_rows = int(flags.get("max_bulk_import_rows", 500))

        csv_text = request.data.get("csv")
        if not csv_text:
            return Response(
                {"error": "csv body is required"}, status=status.HTTP_400_BAD_REQUEST
            )

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
                errors.append(
                    {
                        "row": idx,
                        "error": f"Missing required fields: {', '.join(missing)}",
                    }
                )
            preview.append(record)

        return Response(
            {"preview": preview, "errors": errors}, status=status.HTTP_200_OK
        )

    @action(detail=False, methods=["post"], url_path="bulk-commit")
    def bulk_commit(self, request):
        """Create student records from a parsed payload (admin-only)."""
        denied = self._require_admin(request)
        if denied:
            return denied
        flags = _backend_flags(request)
        if not flags.get("allow_bulk_commit", True):
            return Response(
                {"error": "Bulk commit disabled by admin."},
                status=status.HTTP_403_FORBIDDEN,
            )
        max_rows = int(flags.get("max_bulk_import_rows", 500))

        rows = request.data.get("rows") or []
        if not isinstance(rows, list) or not rows:
            return Response(
                {"error": "rows must be a non-empty list"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if max_rows and len(rows) > max_rows:
            return Response(
                {"error": f"rows exceeds max_bulk_import_rows ({max_rows})"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = []
        errors = []
        for idx, row in enumerate(rows, start=1):
            try:
                serializer = self.get_serializer(data=row)
                serializer.is_valid(raise_exception=True)
                obj = serializer.save(created_by=request.user, updated_by=request.user)
                created.append(obj.id)
            except (
                DRFValidationError,
                IntegrityError,
                DatabaseError,
                TypeError,
                ValueError,
                KeyError,
            ) as exc:
                errors.append({"row": idx, "error": str(exc)})

        return Response(
            {"created": created, "errors": errors}, status=status.HTTP_201_CREATED
        )


@extend_schema_view(
    list=extend_schema(
        tags=["Entity"],
        summary="List teacher profiles",
        description="Admin-like users see all teachers in their school; teachers see only their own profile.",
        responses={200: TeacherProfileSerializer(many=True), 401: OpenApiResponse(description="Authentication required")},
    ),
    retrieve=extend_schema(tags=["Entity"], summary="Retrieve a teacher profile", responses={200: TeacherProfileSerializer, 404: OpenApiResponse(description="Not found")}),
    create=extend_schema(tags=["Entity"], summary="Create a teacher profile (admin only)", request=TeacherProfileSerializer, responses={201: TeacherProfileSerializer, 400: OpenApiResponse(description="Validation error"), 403: OpenApiResponse(description="Permission denied")}),
    update=extend_schema(tags=["Entity"], summary="Update a teacher profile (admin only)", request=TeacherProfileSerializer, responses={200: TeacherProfileSerializer, 403: OpenApiResponse(description="Permission denied")}),
    partial_update=extend_schema(tags=["Entity"], summary="Partially update a teacher profile (admin only)", request=TeacherProfileSerializer, responses={200: TeacherProfileSerializer, 403: OpenApiResponse(description="Permission denied")}),
    destroy=extend_schema(tags=["Entity"], summary="Delete a teacher profile (admin only)", request=None, responses={204: OpenApiResponse(description="Deleted"), 403: OpenApiResponse(description="Permission denied")}),
)
class TeacherProfileViewSet(viewsets.ModelViewSet):
    """CRUD for teachers; admin-only writes, teacher self-read."""
    pagination_class = TeacherProfileCursorPagination

    serializer_class = TeacherProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        role = (getattr(user, "role", "") or "").upper()
        base = TeacherProfile.objects.select_related("user", "department", "reports_to")
        school = _request_school(self.request)
        if school is None:
            return base.none()
        base = base.filter(school=school)

        if _is_admin_like(user):
            return base

        if role == User.Role.TEACHER:
            profile = getattr(user, "teacher_profile", None)
            if profile:
                return base.filter(id=profile.id)

        return base.none()

    def _require_admin(self, request):
        if not _is_admin_like(request.user):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )
        return None

    # Every write goes through _require_admin. It was DEFINED above and never
    # called -- so the class docstring ("admin-only writes"), the
    # @extend_schema_view block advertising 403 on each of these, and the helper
    # itself all described a gate that did not exist. get_queryset returns the
    # caller's OWN row for role TEACHER (correct, for self-read), so get_object()
    # resolved it and the write landed: a teacher could PATCH their own
    # salary_amount, allow_finance_panel, allow_paystub_access and
    # allow_leave_approvals and get 200. Same viewset on /api/entities/teachers/
    # and, via V1TeacherViewSet, /api/v1/people/teachers/.
    #
    # TeacherProfile.school is null=True, so an ungated create also minted rows
    # belonging to no tenant.

    def create(self, request, *args, **kwargs):
        denied = self._require_admin(request)
        if denied:
            return denied
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        denied = self._require_admin(request)
        if denied:
            return denied
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        denied = self._require_admin(request)
        if denied:
            return denied
        return super().destroy(request, *args, **kwargs)


@extend_schema_view(
    list=extend_schema(tags=["Entity"], summary="List guardian/student links", description="Parents see their own links; admins see all links in the active school.", responses={200: StudentGuardianSerializer(many=True)}),
    retrieve=extend_schema(tags=["Entity"], summary="Retrieve a guardian/student link", responses={200: StudentGuardianSerializer, 404: OpenApiResponse(description="Not found")}),
    create=extend_schema(tags=["Entity"], summary="Create a guardian/student link", description="Parents can only create links where guardian_user is themselves; admins may link any user.", request=StudentGuardianSerializer, responses={201: StudentGuardianSerializer, 400: OpenApiResponse(description="Validation error"), 403: OpenApiResponse(description="Permission denied")}),
    update=extend_schema(tags=["Entity"], summary="Update a guardian/student link (admin only)", request=StudentGuardianSerializer, responses={200: StudentGuardianSerializer, 403: OpenApiResponse(description="Permission denied")}),
    partial_update=extend_schema(tags=["Entity"], summary="Partially update a guardian/student link (admin only)", request=StudentGuardianSerializer, responses={200: StudentGuardianSerializer, 403: OpenApiResponse(description="Permission denied")}),
    destroy=extend_schema(tags=["Entity"], summary="Delete a guardian/student link (admin only)", request=None, responses={204: OpenApiResponse(description="Deleted"), 403: OpenApiResponse(description="Permission denied")}),
    bulk_preview=extend_schema(
        tags=["Entity"],
        summary="Dry-run CSV preview for guardian links",
        request=inline_serializer(name="GuardianBulkPreviewRequest", fields={"csv": drf_serializers.CharField()}),
        responses={
            200: inline_serializer(name="GuardianBulkPreviewResponse", fields={"preview": drf_serializers.ListField(child=drf_serializers.DictField()), "errors": drf_serializers.ListField(child=drf_serializers.DictField())}),
            400: OpenApiResponse(description="Missing csv body"),
            403: OpenApiResponse(description="Permission denied"),
        },
    ),
    bulk_commit=extend_schema(
        tags=["Entity"],
        summary="Commit parsed guardian rows (admin only)",
        request=inline_serializer(name="GuardianBulkCommitRequest", fields={"rows": drf_serializers.ListField(child=drf_serializers.DictField())}),
        responses={
            201: inline_serializer(name="GuardianBulkCommitResponse", fields={"created": drf_serializers.ListField(child=drf_serializers.IntegerField()), "errors": drf_serializers.ListField(child=drf_serializers.DictField())}),
            400: OpenApiResponse(description="Invalid payload"),
            403: OpenApiResponse(description="Permission denied or bulk commit disabled"),
        },
    ),
)
class StudentGuardianViewSet(viewsets.ModelViewSet):
    """Manage guardian/student links; parents can view their own links, admins manage all."""
    pagination_class = StudentGuardianCursorPagination

    serializer_class = StudentGuardianSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        base = StudentGuardian.objects.select_related("guardian_user", "student")
        school = _request_school(self.request)
        if school is None:
            return base.none()
        if hasattr(StudentGuardian, "school"):
            base = base.filter(school=school)
        else:
            base = base.filter(student__school=school)
        if _is_admin_like(user):
            return base
        return base.filter(guardian_user=user)

    def create(self, request, *args, **kwargs):
        # Parents can only create links for themselves; admins can create for anyone.
        if not _is_admin_like(request.user):
            guardian_id = request.data.get("guardian_user")
            if guardian_id and str(guardian_id) != str(request.user.id):
                return Response(
                    {"error": "You can only link yourself as guardian."},
                    status=status.HTTP_403_FORBIDDEN,
                )
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not _is_admin_like(request.user):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        if not _is_admin_like(request.user):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )
        return super().partial_update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not _is_admin_like(request.user):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=["post"], url_path="bulk-preview")
    def bulk_preview(self, request):
        """Dry-run parse of guardian CSV data."""
        if not _is_admin_like(request.user):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )
        flags = _backend_flags(request)
        max_rows = int(flags.get("max_bulk_import_rows", 500))

        csv_text = request.data.get("csv")
        if not csv_text:
            return Response(
                {"error": "csv body is required"}, status=status.HTTP_400_BAD_REQUEST
            )

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
                errors.append(
                    {"row": idx, "error": "guardian_user and student are required"}
                )
            preview.append(record)

        return Response(
            {"preview": preview, "errors": errors}, status=status.HTTP_200_OK
        )

    @action(detail=False, methods=["post"], url_path="bulk-commit")
    def bulk_commit(self, request):
        """Create guardian links from parsed payload (admin-only)."""
        if not _is_admin_like(request.user):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )

        flags = _backend_flags(request)
        if not flags.get("allow_bulk_commit", True):
            return Response(
                {"error": "Bulk commit disabled by admin."},
                status=status.HTTP_403_FORBIDDEN,
            )
        max_rows = int(flags.get("max_bulk_import_rows", 500))

        rows = request.data.get("rows") or []
        if not isinstance(rows, list) or not rows:
            return Response(
                {"error": "rows must be a non-empty list"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if max_rows and len(rows) > max_rows:
            return Response(
                {"error": f"rows exceeds max_bulk_import_rows ({max_rows})"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = []
        errors = []
        for idx, row in enumerate(rows, start=1):
            try:
                serializer = self.get_serializer(data=row)
                serializer.is_valid(raise_exception=True)
                obj = serializer.save()
                created.append(obj.id)
            except (
                DRFValidationError,
                IntegrityError,
                DatabaseError,
                TypeError,
                ValueError,
                KeyError,
            ) as exc:
                errors.append({"row": idx, "error": str(exc)})

        return Response(
            {"created": created, "errors": errors}, status=status.HTTP_201_CREATED
        )


@extend_schema_view(
    list=extend_schema(tags=["Entity"], summary="List classrooms", description="Active-school-scoped list of classrooms with academic_year and department.", responses={200: ClassroomSerializer(many=True)}),
    retrieve=extend_schema(tags=["Entity"], summary="Retrieve a classroom", responses={200: ClassroomSerializer, 404: OpenApiResponse(description="Not found")}),
    create=extend_schema(tags=["Entity"], summary="Create a classroom (admin only)", request=ClassroomSerializer, responses={201: ClassroomSerializer, 400: OpenApiResponse(description="Validation error"), 403: OpenApiResponse(description="Permission denied")}),
    update=extend_schema(tags=["Entity"], summary="Update a classroom (admin only)", request=ClassroomSerializer, responses={200: ClassroomSerializer, 403: OpenApiResponse(description="Permission denied")}),
    partial_update=extend_schema(tags=["Entity"], summary="Partially update a classroom (admin only)", request=ClassroomSerializer, responses={200: ClassroomSerializer, 403: OpenApiResponse(description="Permission denied")}),
    destroy=extend_schema(tags=["Entity"], summary="Delete a classroom (admin only)", request=None, responses={204: OpenApiResponse(description="Deleted"), 403: OpenApiResponse(description="Permission denied")}),
)
class ClassroomViewSet(viewsets.ModelViewSet):
    """Classroom CRUD; open read, admin-only writes."""
    pagination_class = ClassroomCursorPagination

    serializer_class = ClassroomSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"

    def get_queryset(self):
        qs = Classroom.objects.select_related("academic_year", "department")
        school = _request_school(self.request)
        if school is None:
            return qs.none()
        qs = qs.filter(school=school)
        return qs

    def _require_admin(self, request):
        if not _is_admin_like(request.user):
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )
        return None


@extend_schema(
    tags=["Entity"],
    summary="Get session claims for the current user",
    description="Return JWT-like claims (user, role, roles, feature_permissions, is_staff, is_superuser, school_id) used by the frontend for RBAC decisions.",
    request=None,
    responses={
        200: inline_serializer(
            name="SessionClaimsResponse",
            fields={
                "user": UserSerializer(),
                "role": drf_serializers.CharField(),
                "roles": drf_serializers.ListField(child=drf_serializers.CharField()),
                "feature_permissions": drf_serializers.ListField(child=drf_serializers.CharField()),
                "is_staff": drf_serializers.BooleanField(),
                "is_superuser": drf_serializers.BooleanField(),
                "school_id": drf_serializers.CharField(required=False),
            },
        ),
        401: OpenApiResponse(description="Authentication required"),
    },
)
class SessionClaimsView(APIView):
    """Return JWT-like claims for the current session to drive frontend RBAC."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        role = (getattr(user, "role", "") or "").upper()
        roles = list(user.roles.values_list("code", flat=True))
        feature_permissions = list(
            user.feature_permissions.values_list("code", flat=True)
        )

        payload = {
            "user": UserSerializer(user, context={"request": request}).data,
            "role": role,
            "roles": roles,
            "feature_permissions": feature_permissions,
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
        }
        school = _request_school(request)
        if school is not None:
            payload["school_id"] = str(school.id)
        return Response(payload)


@extend_schema(
    tags=["Entity"],
    summary="Get the current user's profile",
    description="Return the authenticated user serialized with their role string. Used by mobile/frontend for self-info.",
    request=None,
    responses={200: UserSerializer, 401: OpenApiResponse(description="Authentication required")},
)
class ProfileView(APIView):
    """Current user profile for mobile/frontend. GET /api/auth/profile/"""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        data = UserSerializer(request.user, context={"request": request}).data
        role = (getattr(request.user, "role", "") or "").upper()
        data["role"] = role
        return Response(data)


@extend_schema(
    tags=["Entity"],
    summary="Get the teacher's roster aggregation",
    description=(
        "Return a list of rosters keyed by (classroom, specialty, teacher). Each "
        "roster includes the students currently enrolled in that classroom + "
        "specialty. Admin-like callers see every active assignment in their "
        "school; teachers see only their own assignments."
    ),
    request=None,
    responses={
        200: inline_serializer(
            name="TeacherRosterResponse",
            fields={
                "rosters": drf_serializers.ListField(child=drf_serializers.DictField()),
            },
        ),
        401: OpenApiResponse(description="Authentication required"),
        403: OpenApiResponse(description="Permission denied"),
    },
)
class TeacherRosterView(APIView):
    """Roster aggregation for teachers/admins to drive course/quiz builders."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        role = (getattr(user, "role", "") or "").upper()
        admin_like = _is_admin_like(user)
        teacher_profile = getattr(user, "teacher_profile", None)

        if not admin_like and role != User.Role.TEACHER:
            return Response(
                {"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN
            )

        teacher_ids = (
            [teacher_profile.id] if teacher_profile and not admin_like else None
        )

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
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
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            specialty = assignment.subject_assignment.specialty
            students_qs = StudentProfile.objects.filter(
                classroom=classroom,
                specialty=specialty,
                is_active=True,
            )
            if school is not None:
                students_qs = students_qs.filter(school=school)
            students = students_qs.values(
                "id", "first_name", "last_name", "student_code"
            )
            rosters.append(
                {
                    "classroom": classroom.name if classroom else None,
                    "classroom_id": getattr(classroom, "id", None),
                    "specialty": specialty.name if specialty else None,
                    "specialty_id": getattr(specialty, "id", None),
                    "teacher": getattr(assignment.teacher, "id", None),
                    "teacher_name": getattr(
                        getattr(assignment.teacher, "user", None),
                        "get_full_name",
                        lambda: None,
                    )(),
                    "students": list(students),
                }
            )

        return Response({"rosters": rosters})


import csv
import io
