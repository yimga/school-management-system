"""Move 3 follow-up — pdp_advisory / pdp_enforce decorator tests."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from apps.policies.enforcement import pdp_advisory, pdp_enforce
from apps.policies.models import PolicyDecisionLog, PolicyRule

User = get_user_model()


def _make_request(user):
    factory = RequestFactory()
    req = factory.get("/x/")
    req.user = user
    req.school = None
    return req


class AdvisoryDecoratorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="m3adv", role="TEACHER")

    @override_settings(POLICY_PDP_ENFORCEMENT_MODE="advisory")
    def test_advisory_never_blocks_and_logs(self):
        @pdp_advisory(action="read", resource_kind="student")
        def view(request, pk=None):
            return HttpResponse("ok")

        before = PolicyDecisionLog.objects.count()
        resp = view(_make_request(self.user))
        after = PolicyDecisionLog.objects.count()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(after - before, 1)
        # No rules exist → implicit_deny was logged but the view still ran.
        latest = PolicyDecisionLog.objects.order_by("-created_at").first()
        self.assertEqual(latest.effect, "implicit_deny")

    @override_settings(POLICY_PDP_ENFORCEMENT_MODE="off")
    def test_off_short_circuits(self):
        @pdp_advisory(action="read", resource_kind="student")
        def view(request, pk=None):
            return HttpResponse("ok")

        before = PolicyDecisionLog.objects.count()
        view(_make_request(self.user))
        after = PolicyDecisionLog.objects.count()
        self.assertEqual(after - before, 0)


class EnforceDecoratorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="m3enf", role="TEACHER")

    @override_settings(POLICY_PDP_ENFORCEMENT_MODE="enforce")
    def test_enforce_blocks_on_implicit_deny(self):
        @pdp_enforce(action="read", resource_kind="student")
        def view(request, pk=None):
            return HttpResponse("ok")

        with self.assertRaises(PermissionDenied):
            view(_make_request(self.user))

    @override_settings(POLICY_PDP_ENFORCEMENT_MODE="enforce")
    def test_enforce_allows_when_rule_matches(self):
        PolicyRule.objects.create(
            code="teachers_read_students",
            name="x",
            effect=PolicyRule.Effect.ALLOW,
            subject_match={"role": "TEACHER"},
            action_match={"actions": ["read"]},
            resource_match={"entity": "student"},
            priority=10,
        )

        @pdp_enforce(action="read", resource_kind="student")
        def view(request, pk=None):
            return HttpResponse("ok")

        resp = view(_make_request(self.user))
        self.assertEqual(resp.status_code, 200)

    @override_settings(POLICY_PDP_ENFORCEMENT_MODE="advisory")
    def test_enforce_decorator_in_advisory_mode_does_not_block(self):
        @pdp_enforce(action="read", resource_kind="student")
        def view(request, pk=None):
            return HttpResponse("ok")

        resp = view(_make_request(self.user))  # no rule, would be deny in enforce mode
        self.assertEqual(resp.status_code, 200)
