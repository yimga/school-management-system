"""Phase 8: tenant security trust hub + impersonation audit."""

import uuid

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.accounts.views_trust_hub import security_trust_hub, tenant_impersonation_audit
from apps.siteconfig.models import ImpersonationLog
from apps.schools.models import School

User = get_user_model()


class SecurityTrustHubTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Trust School",
            slug=f"tr-{uuid.uuid4().hex[:10]}",
            subdomain=f"tr-{uuid.uuid4().hex[:10]}",
        )
        self.admin = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:8]}",
            email="adm@t.test",
            password="x",
            role=User.Role.ADMIN,
        )
        self.factory = RequestFactory()

    def test_hub_requires_school(self):
        req = self.factory.get("/authentication/backend/security-trust/")
        req.user = self.admin
        resp = security_trust_hub(req)
        self.assertEqual(resp.status_code, 403)

    def test_hub_ok_for_admin_with_school(self):
        req = self.factory.get("/authentication/backend/security-trust/")
        req.user = self.admin
        req.school = self.school
        resp = security_trust_hub(req)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Security")
        # Leadership sees policy / feature enforcement deep links
        self.assertContains(resp, "Feature control")

    def test_impersonation_audit_forbidden_for_teacher(self):
        t = User.objects.create_user(
            username=f"te-{uuid.uuid4().hex[:8]}",
            email="te@t.test",
            password="x",
            role=User.Role.TEACHER,
        )
        req = self.factory.get("/authentication/backend/security-trust/impersonation/")
        req.user = t
        req.school = self.school
        resp = tenant_impersonation_audit(req)
        self.assertEqual(resp.status_code, 403)

    def test_impersonation_audit_lists_rows(self):
        ImpersonationLog.objects.create(
            actor=self.admin,
            school=self.school,
            action=ImpersonationLog.Action.SWITCH,
            reason="test",
        )
        req = self.factory.get("/authentication/backend/security-trust/impersonation/")
        req.user = self.admin
        req.school = self.school
        resp = tenant_impersonation_audit(req)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Switch to tenant")
