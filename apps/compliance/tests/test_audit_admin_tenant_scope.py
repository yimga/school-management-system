"""The four membership-scoped audit changelists must not render another tenant's rows.

``AuditLog``, ``AccessLog``, ``UserActivitySession`` and ``ComplianceReport`` are
registered on ``tenant_admin_site`` and have NO ``school`` column — they are
scoped by who the actor is (``apps/compliance/tenant_scope.py``). That means
``config.admin._TenantScopedQuerysetMixin``, which filters on a concrete
``school`` field, can never apply to them, and their physical tables live in
``public`` where a tenant schema's ``search_path`` reaches every tenant's rows.
So an unscoped changelist here is a one-click cross-tenant read — and
``AuditLogAdmin`` carries CSV/JSON export actions over whatever it lists.

``config/admin.py`` classifies all four in ``TENANT_ADMIN_ACTOR_SCOPE`` and
auto-applies ``_TenantActorScopedQuerysetMixin`` at registration. These tests
assert the resulting BEHAVIOUR from the compliance side, so the seal cannot be
removed silently by an edit to the central registry.
"""

from datetime import date

from django.contrib.messages.storage.base import BaseStorage
from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.compliance.models_audit import (
    AccessLog,
    AuditLog,
    ComplianceReport,
    UserActivitySession,
)
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import RegionConfig
from config.admin import tenant_admin_site


class _NullMessages(BaseStorage):
    """Message sink so an admin action can be called without MessageMiddleware."""

    def _get(self, *args, **kwargs):
        return [], True

    def _store(self, messages, response, *args, **kwargs):
        return []


class AuditChangelistTenantScopeTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.region = RegionConfig.get_default()
        self.school_a = School.objects.create(
            slug="audit-scope-a",
            subdomain="audit-scope-a",
            name="Audit Scope A",
            default_region=self.region,
            timezone=self.region.timezone,
        )
        self.school_b = School.objects.create(
            slug="audit-scope-b",
            subdomain="audit-scope-b",
            name="Audit Scope B",
            default_region=self.region,
            timezone=self.region.timezone,
        )
        self.admin_a = self._member("audit_scope_admin_a", self.school_a)
        self.actor_a = self._member("audit_scope_actor_a", self.school_a)
        self.actor_b = self._member("audit_scope_actor_b", self.school_b)

        # One row per model per school, authored by a NON-requesting user, so the
        # mixin's "your own rows are always yours" carve-out cannot mask a leak.
        self.rows = {}
        for label, actor in (("a", self.actor_a), ("b", self.actor_b)):
            self.rows[("auditlog", label)] = AuditLog.objects.create(
                user=actor,
                action=AuditLog.Action.VIEW,
                model_name="StudentProfile",
                object_id="1",
                object_repr=f"Student of school {label}",
                app_label="people",
                sensitivity=AuditLog.Sensitivity.CRITICAL,
            )
            self.rows[("accesslog", label)] = AccessLog.objects.create(
                user=actor,
                access_type=AccessLog.AccessType.WEB,
                resource=f"/school-{label}/students/",
                status=AccessLog.Status.SUCCESS,
            )
            self.rows[("session", label)] = UserActivitySession.objects.create(
                user=actor,
                session_key=f"audit-scope-session-{label}",
                ip_address="203.0.113.1",
            )
            self.rows[("report", label)] = ComplianceReport.objects.create(
                report_type=ComplianceReport.ReportType.AUDIT_TRAIL,
                generated_by=actor,
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
                summary={"school": label},
                details={},
            )

    def _member(self, username, school):
        user = User.objects.create_user(
            username=username, password="pass12345", role=User.Role.ADMIN
        )
        SchoolMembership.objects.create(
            user=user, school=school, role=User.Role.ADMIN, is_primary=True
        )
        return user

    def _request(self):
        request = self.factory.get("/admin/")
        request.user = self.admin_a
        # Without this the changelist has no tenant at all and fails closed, so
        # "school B is absent" would pass against fully unscoped code.
        request.school = self.school_a
        return request

    def _changelist(self, model):
        model_admin = tenant_admin_site._registry.get(model)
        self.assertIsNotNone(
            model_admin, f"{model.__name__} is not registered on the tenant admin"
        )
        return model_admin.get_queryset(self._request())

    def test_each_audit_changelist_shows_only_this_school(self):
        for key, model in (
            ("auditlog", AuditLog),
            ("accesslog", AccessLog),
            ("session", UserActivitySession),
            ("report", ComplianceReport),
        ):
            with self.subTest(model=model.__name__):
                pks = set(self._changelist(model).values_list("pk", flat=True))
                # Present: otherwise a .none() queryset would pass vacuously.
                self.assertIn(
                    self.rows[(key, "a")].pk,
                    pks,
                    "this school's own audit rows must still be visible",
                )
                self.assertNotIn(
                    self.rows[(key, "b")].pk,
                    pks,
                    "another school's audit rows must never appear on this changelist",
                )

    def test_changelist_fails_closed_without_a_school(self):
        """No resolvable tenant means no rows — never the whole public table."""
        request = self.factory.get("/admin/")
        request.user = self.admin_a
        request.school = None
        for model in (AuditLog, AccessLog, UserActivitySession, ComplianceReport):
            with self.subTest(model=model.__name__):
                model_admin = tenant_admin_site._registry[model]
                self.assertFalse(model_admin.get_queryset(request).exists())

    def test_export_action_serialises_only_the_scoped_changelist(self):
        """AuditLogAdmin's CSV export runs over the changelist queryset.

        The export is what turns a wide changelist into a cross-tenant dump, so
        it is asserted against the scoped queryset rather than the raw manager.
        """
        model_admin = tenant_admin_site._registry[AuditLog]
        request = self._request()
        request._messages = _NullMessages(request)
        response = model_admin.export_audit_log_csv(
            request, model_admin.get_queryset(request)
        )
        body = response.content.decode("utf-8")
        self.assertIn("Student of school a", body)
        self.assertNotIn("Student of school b", body)
