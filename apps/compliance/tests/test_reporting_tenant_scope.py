import json
from datetime import timedelta

from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.compliance.models_audit import AccessLog, AuditLog
from apps.compliance.views_reporting import ExportComplianceReportView
from apps.schools.models import School, SchoolMembership
from apps.siteconfig.models import RegionConfig


class ComplianceReportingTenantScopeTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.region = RegionConfig.get_default()
        self.school = School.objects.create(
            slug="compliance-scope-school",
            subdomain="compliance-scope-school",
            name="Compliance Scope School",
            default_region=self.region,
            timezone=self.region.timezone,
        )
        self.other_school = School.objects.create(
            slug="compliance-scope-other",
            subdomain="compliance-scope-other",
            name="Compliance Scope Other",
            default_region=self.region,
            timezone=self.region.timezone,
        )
        self.admin = User.objects.create_user(
            username="compliance_scope_admin",
            password="pass12345",
            role=User.Role.ADMIN,
        )
        self.other_admin = User.objects.create_user(
            username="compliance_scope_other",
            password="pass12345",
            role=User.Role.ADMIN,
        )
        SchoolMembership.objects.create(user=self.admin, school=self.school, role=User.Role.ADMIN, is_primary=True)
        SchoolMembership.objects.create(user=self.other_admin, school=self.other_school, role=User.Role.ADMIN, is_primary=True)

        now = timezone.now()
        AuditLog.objects.create(
            user=self.admin,
            action=AuditLog.Action.VIEW,
            model_name="Invoice",
            object_id="1",
            object_repr="Tenant Invoice",
            sensitivity=AuditLog.Sensitivity.MEDIUM,
            app_label="finance",
            timestamp=now - timedelta(hours=1),
        )
        AuditLog.objects.create(
            user=self.other_admin,
            action=AuditLog.Action.VIEW,
            model_name="Invoice",
            object_id="2",
            object_repr="Other Invoice",
            sensitivity=AuditLog.Sensitivity.MEDIUM,
            app_label="finance",
            timestamp=now - timedelta(hours=1),
        )
        AccessLog.objects.create(
            user=self.admin,
            access_type=AccessLog.AccessType.API,
            resource="/api/finance/invoices/",
            status="200",
            request_method="GET",
            timestamp=now - timedelta(hours=1),
        )
        AccessLog.objects.create(
            user=self.other_admin,
            access_type=AccessLog.AccessType.API,
            resource="/api/finance/invoices/",
            status="403",
            request_method="GET",
            timestamp=now - timedelta(hours=1),
        )

    def test_export_json_is_scoped_to_request_school(self):
        request = self.factory.get("/compliance/export/", {"type": "audit_trail", "format": "json", "days": "30"})
        request.user = self.admin
        request.school = self.school

        response = ExportComplianceReportView.as_view()(request)
        payload = json.loads(response.content.decode("utf-8"))

        usernames = {row["user__username"] for row in payload}
        self.assertEqual(usernames, {self.admin.username})
