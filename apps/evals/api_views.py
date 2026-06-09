"""Tenant-scoped evaluation CRUD for platform API v1."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.api.entity_api import _request_school
from apps.api.permissions import MarketplaceAppScopedPermission
from apps.evals.models import Evaluation


class EvaluationSerializer:
    """Lazy import wrapper — real serializer defined inline to avoid circular imports."""

    pass


def _evaluation_serializer_class():
    from rest_framework import serializers

    class _Ser(serializers.ModelSerializer):
        class Meta:
            model = Evaluation
            fields = (
                "id",
                "school",
                "academic_year",
                "term",
                "subject_assignment",
                "student",
                "teacher",
                "seq1_score",
                "seq2_score",
                "exam_score",
                "final_score",
                "letter_grade",
                "updated_at",
            )
            read_only_fields = ("id", "school", "final_score", "updated_at")

    return _Ser


@extend_schema_view(
    list=extend_schema(tags=["Platform v1 — Evals"]),
    retrieve=extend_schema(tags=["Platform v1 — Evals"]),
    create=extend_schema(tags=["Platform v1 — Evals"]),
    update=extend_schema(tags=["Platform v1 — Evals"]),
    partial_update=extend_schema(tags=["Platform v1 — Evals"]),
    destroy=extend_schema(tags=["Platform v1 — Evals"]),
)
class EvaluationViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, MarketplaceAppScopedPermission]
    basename = "evaluations"

    def get_serializer_class(self):
        return _evaluation_serializer_class()

    def get_queryset(self):
        school = _request_school(self.request)
        if school is None:
            return Evaluation.objects.none()
        return Evaluation.objects.filter(school=school).select_related(
            "student", "teacher", "term", "academic_year", "subject_assignment"
        )

    def perform_create(self, serializer):
        school = _request_school(self.request)
        serializer.save(school=school)
