"""multi-campus-network applies end-to-end through governed approval.

The operator-network blueprint sat at ``status="preview_ready"`` long after its
contract was complete. That status is not a soft label: ``preview_blueprint``
raises a ``not_installable`` conflict for it, which sets ``can_apply=False``,
and BOTH apply paths check ``can_apply`` — the direct one and the approved
change-request one (which re-reads the stored preview snapshot). So the
blueprint was un-appliable by anyone, forever, including a platform operator
with an approved request. Its readiness meter read 20.

These tests are what licensed flipping it to ``installable``: they prove the
governed path actually completes, and — just as importantly — that flipping the
status did NOT widen access. The operator-approval gate and the tenant block
are asserted here, so a future "make it easier to apply" change cannot quietly
turn a cross-tenant, operator-owned blueprint into a self-service tenant one.
"""
from __future__ import annotations

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.blueprint_apply import apply_blueprint
from apps.platform_runtime.blueprint_contract import list_blueprints
from apps.platform_runtime.blueprint_preview import preview_blueprint
from apps.platform_runtime.configuration_change_requests import (
    apply_approved_change_request,
    approve_change_request,
    create_change_request,
)
from apps.platform_runtime.configuration_change_set import generate_blueprint_change_set
from apps.platform_runtime.models import BlueprintInstallation, ConfigurationChangeRequest
from apps.schools.models import School

BLUEPRINT = "multi-campus-network"


class MultiCampusNetworkApplyTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Network Campus One",
            slug="network-campus-one",
            subdomain="network-campus-one",
            is_active=True,
            settings={},
        )
        self.operator = User.objects.create_user(
            username="network_operator",
            password="x" * 12,
            is_staff=True,
            is_superuser=True,
        )

    def test_applies_end_to_end_through_approved_change_request(self):
        change_set = generate_blueprint_change_set(
            BLUEPRINT, school=self.school, actor=self.operator, platform_operator=True
        )
        self.assertTrue(
            change_set["can_apply"],
            msg=f"Preview must clear before approval: {change_set['conflicts']}",
        )

        change_request = create_change_request(
            ConfigurationChangeRequest.RequestType.BLUEPRINT_APPLY,
            target_key=BLUEPRINT,
            target_type="blueprint",
            school=self.school,
            actor=self.operator,
            reason="Network rollout",
            platform_operator=True,
        )
        self.assertEqual(
            change_request.status,
            ConfigurationChangeRequest.Status.PENDING_APPROVAL,
        )

        approve_change_request(change_request, actor=self.operator, notes="approved")
        result = apply_approved_change_request(change_request, actor=self.operator)

        self.assertTrue(result.get("ok"), msg=result)
        installation = BlueprintInstallation.objects.get(pk=result["installation_id"])
        self.assertEqual(installation.blueprint_key, BLUEPRINT)
        self.assertEqual(installation.status, BlueprintInstallation.Status.APPLIED)
        self.assertEqual(installation.school_id, self.school.pk)
        change_request.refresh_from_db()
        self.assertEqual(
            change_request.status, ConfigurationChangeRequest.Status.APPLIED
        )

    def test_governance_gate_did_not_widen_on_direct_apply(self):
        # No approved change request (hence no idempotency key) → refused, even
        # for a platform operator. Installable status must not become a bypass.
        result = apply_blueprint(
            BLUEPRINT,
            school=self.school,
            actor=self.operator,
            confirmed=True,
            platform_operator=True,
        )

        self.assertFalse(result.get("ok"), msg=result)
        self.assertFalse(
            BlueprintInstallation.objects.filter(blueprint_key=BLUEPRINT).exists()
        )

    def test_tenant_can_neither_see_nor_apply_it(self):
        self.assertNotIn(
            BLUEPRINT,
            {row["key"] for row in list_blueprints(tenant_safe_only=True)},
            msg="Operator-network blueprint must stay out of the tenant catalog.",
        )

        preview = preview_blueprint(
            BLUEPRINT, school=self.school, platform_operator=False
        )

        self.assertFalse(preview["can_apply"])
        codes = {conflict["code"] for conflict in preview["conflicts"]}
        self.assertIn("platform_operator_required", codes)
        self.assertIn("tenant_blocked", codes)
