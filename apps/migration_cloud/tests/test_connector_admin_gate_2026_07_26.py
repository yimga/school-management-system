"""The Migration Cloud connector wizard is tenant-admin gated (+ operator view fixed).

The hole: every view in ``views_connectors.py`` was ``(LoginRequiredMixin, ...)``
with no role check, and the wizard is TENANT-HOST-ONLY and drives imports that
overwrite the school's live data. Because SAML/SCIM provisions a membership for
every IdP user, the effective gate was "authenticated + any membership" — so a
teacher / parent / student could connect a source and run an import. Now every
connector view requires the tenant-admin tier of the request's own school.

Separately, ``MigrationCloudConnectorOperatorView`` (the cross-tenant operator
dashboard) gated on bare ``is_staff`` — which the platform mints for tenant
admins — so any tenant admin could read every school's connections + imports.
It now gates on genuine control-plane access.

RequestFactory drives the views directly — the host-split urlconf makes a Client
test mass-false-RED.
"""

from __future__ import annotations

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.decorators import user_is_tenant_admin
from apps.accounts.models import User
from apps.migration_cloud.views_connectors import (
    _ConnectorTenantAdminRequiredMixin,
    MigrationCloudConnectorConnectView,
    MigrationCloudConnectorDiscoverView,
    MigrationCloudConnectorHomeView,
    MigrationCloudConnectorImportView,
    MigrationCloudConnectorMappingView,
    MigrationCloudConnectorOperatorView,
    MigrationCloudConnectorQuarantineView,
    MigrationCloudConnectorReviewView,
    MigrationCloudConnectorRevokeView,
    MigrationCloudConnectorValidateView,
)
from apps.schools.models import School, SchoolMembership

_CONNECTOR_WRITE_VIEWS = (
    MigrationCloudConnectorHomeView,
    MigrationCloudConnectorConnectView,
    MigrationCloudConnectorDiscoverView,
    MigrationCloudConnectorMappingView,
    MigrationCloudConnectorValidateView,
    MigrationCloudConnectorQuarantineView,
    MigrationCloudConnectorImportView,
    MigrationCloudConnectorReviewView,
    MigrationCloudConnectorRevokeView,
)


@override_settings(ALLOWED_HOSTS=["*"], ROOT_URLCONF="config.tenant_urls")
class ConnectorWizardAdminGateTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Connector Gate", slug="connector-gate", subdomain="connector-gate",
            is_active=True,
        )
        self.member = User.objects.create_user(
            username="conn-member", password="x", role=User.Role.TEACHER, is_staff=False
        )
        SchoolMembership.objects.create(
            user=self.member, school=self.school, role=User.Role.TEACHER,
            is_school_owner=False, is_primary=True,
        )
        self.admin = User.objects.create_user(
            username="conn-admin", password="x", role=User.Role.ADMIN, is_staff=False
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role=User.Role.ADMIN,
            is_school_owner=False, is_primary=True,
        )

    def _req(self, user, method="post", data=None):
        request = getattr(self.factory, method)("/school/setup/migration-cloud/connect/", data or {})
        request.user = user
        request.school = self.school
        request.session = {}
        request._messages = FallbackStorage(request)
        return request

    def test_non_admin_member_is_denied_at_the_connector_gate(self):
        # GET (not POST) so the tenant-admin gate — not csrf_protect on the POST
        # path — is what fires. The mixin blocks every method, GET included.
        self.assertFalse(user_is_tenant_admin(self.member, self.school))
        with self.assertRaises(PermissionDenied):
            MigrationCloudConnectorConnectView.as_view()(self._req(self.member, method="get"))

    def test_admin_passes_the_connector_gate(self):
        # The gate must NOT raise PermissionDenied for a tenant admin. The view body
        # may still fail (missing form data / template context); we only assert the
        # tenant-admin gate itself lets the admin through.
        self.assertTrue(user_is_tenant_admin(self.admin, self.school))
        try:
            MigrationCloudConnectorConnectView.as_view()(self._req(self.admin, method="get"))
        except PermissionDenied:
            self.fail("tenant admin was denied by the connector gate")
        except Exception:
            pass  # any non-PermissionDenied outcome is past the gate

    def test_every_connector_view_carries_the_admin_gate(self):
        for view in _CONNECTOR_WRITE_VIEWS:
            self.assertIn(_ConnectorTenantAdminRequiredMixin, view.__mro__, view.__name__)


class ConnectorOperatorViewControlPlaneGateTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def _req(self, user):
        request = self.factory.get("/super/migration/connector/operator/")
        request.user = user
        return request

    def test_is_staff_tenant_admin_is_not_treated_as_operator(self):
        staff_admin = User.objects.create_user(
            username="op-staffadmin", password="x", is_staff=True
        )
        with self.assertRaises(Http404):
            MigrationCloudConnectorOperatorView.as_view()(self._req(staff_admin))

    def test_control_plane_operator_passes_the_gate(self):
        operator = User.objects.create_superuser(
            username="op-super", password="x", email="op@example.com"
        )
        try:
            MigrationCloudConnectorOperatorView.as_view()(self._req(operator))
        except Http404:
            self.fail("control-plane operator was 404'd by the operator gate")
        except Exception:
            pass  # past the gate; the body/template may need more context
