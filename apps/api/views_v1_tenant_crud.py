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
from apps.api.throttling import ApiReadWriteThrottle, ApiSoftWarnHeaderMixin
from apps.evals.api_views import EvaluationViewSet
from apps.finance.api_views import InvoiceViewSet, PaymentViewSet


def _v1_permission_classes():
    return [IsAuthenticated, MarketplaceAppScopedPermission]


#: Method-aware scoped throttle — reads + writes budgeted independently,
#: per user, per tenant. Listed once per viewset so DRF runs it on every
#: action.
_V1_THROTTLE_CLASSES = [ApiReadWriteThrottle]


@extend_schema_view()
class V1StudentViewSet(ApiSoftWarnHeaderMixin, StudentProfileViewSet):
    basename = "students"
    permission_classes = _v1_permission_classes()
    throttle_classes = _V1_THROTTLE_CLASSES


@extend_schema_view()
class V1TeacherViewSet(ApiSoftWarnHeaderMixin, TeacherProfileViewSet):
    basename = "teachers"
    permission_classes = _v1_permission_classes()
    throttle_classes = _V1_THROTTLE_CLASSES


@extend_schema_view()
class V1GuardianViewSet(ApiSoftWarnHeaderMixin, StudentGuardianViewSet):
    basename = "guardians"
    permission_classes = _v1_permission_classes()
    throttle_classes = _V1_THROTTLE_CLASSES


@extend_schema_view()
class V1EvaluationViewSet(ApiSoftWarnHeaderMixin, EvaluationViewSet):
    basename = "evaluations"
    permission_classes = _v1_permission_classes()
    throttle_classes = _V1_THROTTLE_CLASSES


@extend_schema_view()
class V1InvoiceViewSet(ApiSoftWarnHeaderMixin, InvoiceViewSet):
    basename = "invoices"
    permission_classes = _v1_permission_classes()
    throttle_classes = _V1_THROTTLE_CLASSES


@extend_schema_view()
class V1PaymentViewSet(ApiSoftWarnHeaderMixin, PaymentViewSet):
    basename = "payments"
    permission_classes = _v1_permission_classes()
    throttle_classes = _V1_THROTTLE_CLASSES
