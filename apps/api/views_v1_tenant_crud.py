"""Platform API v1 — scoped tenant CRUD for people, evals, finance."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_view
from rest_framework.permissions import IsAuthenticated

from apps.api.entity_api import (
    StudentGuardianViewSet,
    StudentProfileViewSet,
    TeacherProfileViewSet,
)
from apps.api.permissions import MarketplaceAppScopedPermission
from apps.evals.api_views import EvaluationViewSet
from apps.finance.api_views import InvoiceViewSet, PaymentViewSet


def _v1_permission_classes():
    return [IsAuthenticated, MarketplaceAppScopedPermission]


@extend_schema_view()
class V1StudentViewSet(StudentProfileViewSet):
    basename = "students"
    permission_classes = _v1_permission_classes()


@extend_schema_view()
class V1TeacherViewSet(TeacherProfileViewSet):
    basename = "teachers"
    permission_classes = _v1_permission_classes()


@extend_schema_view()
class V1GuardianViewSet(StudentGuardianViewSet):
    basename = "guardians"
    permission_classes = _v1_permission_classes()


@extend_schema_view()
class V1EvaluationViewSet(EvaluationViewSet):
    basename = "evaluations"
    permission_classes = _v1_permission_classes()


@extend_schema_view()
class V1InvoiceViewSet(InvoiceViewSet):
    basename = "invoices"
    permission_classes = _v1_permission_classes()


@extend_schema_view()
class V1PaymentViewSet(PaymentViewSet):
    basename = "payments"
    permission_classes = _v1_permission_classes()
