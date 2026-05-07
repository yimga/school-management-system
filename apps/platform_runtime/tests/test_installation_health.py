from __future__ import annotations

from django.test import TestCase

from apps.platform_runtime.installation_health import calculate_pack_installation_health
from apps.platform_runtime.models import ConfigurationChangeRequest, PackInstallation
from apps.schools.models import School


class InstallationHealthTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Health School", slug="health-school", subdomain="health-school", is_active=True)

    def test_health_reports_external_failed_and_pending(self):
        external = PackInstallation.objects.create(
            school=self.school,
            pack_key="finance-approval",
            pack_type="policy_bundle",
            version="1.0.0",
            status=PackInstallation.Status.APPLIED,
            external_blockers=["PSP proof"],
            idempotency_key="external",
        )
        self.assertEqual(calculate_pack_installation_health(external)["state"], "external_blocked")

        failed = PackInstallation.objects.create(
            school=self.school,
            pack_key="failed-pack",
            pack_type="workflow_pack",
            version="1.0.0",
            status=PackInstallation.Status.FAILED,
            idempotency_key="failed",
        )
        self.assertEqual(calculate_pack_installation_health(failed)["state"], "failed")

        pending = PackInstallation.objects.create(
            school=self.school,
            pack_key="network-operator",
            pack_type="dashboard_pack",
            version="1.0.0",
            status=PackInstallation.Status.PREVIEWED,
            idempotency_key="pending",
        )
        ConfigurationChangeRequest.objects.create(
            school=self.school,
            request_type=ConfigurationChangeRequest.RequestType.PACK_APPLY,
            target_key="network-operator",
            target_type="dashboard_pack",
            target_version="1.0.0",
            status=ConfigurationChangeRequest.Status.PENDING_APPROVAL,
            idempotency_key="pending-request",
        )
        self.assertEqual(calculate_pack_installation_health(pending)["state"], "pending_approval")
