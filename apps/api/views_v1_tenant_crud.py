"""Platform API v1 — scoped tenant CRUD for people, evals, finance."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_view
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.api.entity_api import (
    StudentGuardianViewSet,
    StudentProfileViewSet,
    TeacherProfileViewSet,
)
from apps.api.permissions import MarketplaceAppScopedPermission
from apps.api.third_party_auth import (
    ThirdPartyCredentialAuthentication,
    ThirdPartyScopePermission,
)
from apps.api.throttling import ApiReadWriteThrottle, ApiSoftWarnHeaderMixin
from apps.evals.api_views import EvaluationViewSet
from apps.finance.api_views import InvoiceViewSet, PaymentViewSet


def _v1_authentication_classes():
    """Program item 4.1 — let a third-party credential authenticate here.

    ``ThirdPartyCredentialAuthentication`` MUST come first: ``JWTAuthentication``
    claims any ``Authorization: Bearer …`` header and hard-fails on a value that
    is not a JWT, which is why a presented API key previously never reached a
    resolver at all. The two settings defaults follow it unchanged, so session
    and JWT callers behave exactly as before.
    """
    return [
        ThirdPartyCredentialAuthentication,
        SessionAuthentication,
        JWTAuthentication,
    ]


def _v1_permission_classes():
    """Deny-by-default scope gate layered on the existing permission stack.

    ``ThirdPartyScopePermission`` is a no-op for session/JWT callers and gates
    third-party credentials against ``V1_TENANT_CRUD_SCOPE_MAP``. It is required
    in addition to ``MarketplaceAppScopedPermission`` because that class keys off
    ``request.app_installation`` and therefore waves through a credential that
    carries no marketplace installation.
    """
    return [IsAuthenticated, MarketplaceAppScopedPermission, ThirdPartyScopePermission]


#: Method-aware scoped throttle — reads + writes budgeted independently,
#: per user, per tenant. Listed once per viewset so DRF runs it on every
#: action.
_V1_THROTTLE_CLASSES = [ApiReadWriteThrottle]

#: Scope gates that must run on every v1 CRUD action, whatever else the parent
#: viewset decides about role-based access.
_V1_SCOPE_GATES = (MarketplaceAppScopedPermission, ThirdPartyScopePermission)


class _V1ScopeGateMixin:
    """Keep the scope gates reachable on parents that override ``get_permissions``.

    DRF's ``get_permissions`` is the only thing the dispatcher calls;
    ``permission_classes`` is merely its default source. ``InvoiceViewSet`` and
    ``PaymentViewSet`` both *override* ``get_permissions`` to pick a Rebac
    permission per action, which discards ``permission_classes`` wholesale — so
    the scope map's ``finance:read`` / ``finance:write`` entries were
    structurally unreachable, and a scoped credential would have read the
    finance surface with no scope check at all.

    This mixin appends the gates to whatever the parent returns, so parent RBAC
    is preserved and the scope check is added on top rather than replacing it.
    Appending is idempotent — gates already present are not duplicated.
    """

    def get_permissions(self):
        resolved = list(super().get_permissions())
        present = {type(p) for p in resolved}
        resolved.extend(gate() for gate in _V1_SCOPE_GATES if gate not in present)
        return resolved


@extend_schema_view()
class V1StudentViewSet(ApiSoftWarnHeaderMixin, _V1ScopeGateMixin, StudentProfileViewSet):
    basename = "students"
    authentication_classes = _v1_authentication_classes()
    permission_classes = _v1_permission_classes()
    throttle_classes = _V1_THROTTLE_CLASSES


@extend_schema_view()
class V1TeacherViewSet(ApiSoftWarnHeaderMixin, _V1ScopeGateMixin, TeacherProfileViewSet):
    basename = "teachers"
    authentication_classes = _v1_authentication_classes()
    permission_classes = _v1_permission_classes()
    throttle_classes = _V1_THROTTLE_CLASSES


@extend_schema_view()
class V1GuardianViewSet(ApiSoftWarnHeaderMixin, _V1ScopeGateMixin, StudentGuardianViewSet):
    basename = "guardians"
    authentication_classes = _v1_authentication_classes()
    permission_classes = _v1_permission_classes()
    throttle_classes = _V1_THROTTLE_CLASSES


@extend_schema_view()
class V1EvaluationViewSet(ApiSoftWarnHeaderMixin, _V1ScopeGateMixin, EvaluationViewSet):
    basename = "evaluations"
    authentication_classes = _v1_authentication_classes()
    permission_classes = _v1_permission_classes()
    throttle_classes = _V1_THROTTLE_CLASSES


@extend_schema_view()
class V1InvoiceViewSet(ApiSoftWarnHeaderMixin, _V1ScopeGateMixin, InvoiceViewSet):
    basename = "invoices"
    authentication_classes = _v1_authentication_classes()
    permission_classes = _v1_permission_classes()
    throttle_classes = _V1_THROTTLE_CLASSES


@extend_schema_view()
class V1PaymentViewSet(ApiSoftWarnHeaderMixin, _V1ScopeGateMixin, PaymentViewSet):
    basename = "payments"
    authentication_classes = _v1_authentication_classes()
    permission_classes = _v1_permission_classes()
    throttle_classes = _V1_THROTTLE_CLASSES
