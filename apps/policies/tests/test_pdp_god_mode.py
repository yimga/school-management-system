"""Wave D — platform superadmin god-mode at the PDP.

The PDP defaults to ``implicit_deny`` when no rule matches. Before the fix it had no
superuser branch, so promoting PDP from advisory to hard-enforce would have DENIED
the platform superadmin any resource without an explicit allow rule. A Django
superuser must never be bounded by tenant policy.
"""

from django.test import TestCase

from apps.accounts.models import User
from apps.policies.pdp import decide


class PdpSuperuserGodModeTests(TestCase):
    def setUp(self):
        self.su = User.objects.create_user(
            username="pdpsu", password="x", is_superuser=True, is_staff=True
        )
        self.teacher = User.objects.create_user(
            username="pdpt", password="x", role=User.Role.TEACHER
        )

    def test_superuser_by_id_is_allowed(self):
        d = decide(
            {"user_id": self.su.id, "role": "SUPERADMIN"},
            "write",
            {"entity": "student", "field": "ssn", "sensitivity_tier": "restricted"},
        )
        self.assertTrue(d.allowed)
        self.assertEqual(d.effect, "allow")

    def test_superuser_by_flag_is_allowed(self):
        d = decide(
            {"is_superuser": True, "role": "X"},
            "delete",
            {"entity": "invoice"},
        )
        self.assertTrue(d.allowed)

    def test_normal_user_default_denies_restricted(self):
        d = decide(
            {"user_id": self.teacher.id, "role": "TEACHER"},
            "write",
            {"entity": "student", "field": "ssn", "sensitivity_tier": "restricted"},
        )
        self.assertFalse(d.allowed)
