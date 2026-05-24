from django.contrib.auth import get_user_model
from django.test import SimpleTestCase

from apps.accounts.profile_security_evaluation import (
    evaluate_profile_security,
    evaluate_user_profile_security,
    strength_band,
)

User = get_user_model()


class ProfileSecurityEvaluationTests(SimpleTestCase):
    def test_mfa_disabled_caps_score(self):
        result = evaluate_profile_security(
            {
                "mfa_enabled": False,
                "email_verified": True,
                "has_email": True,
                "password_expired": False,
                "password_strength_ok": True,
                "has_passkey": True,
                "has_recovery": True,
                "phone_verified": True,
                "session_count_high": False,
                "profile": {
                    "has_photo": True,
                    "has_first_name": True,
                    "has_last_name": True,
                    "has_phone": True,
                },
            }
        )
        self.assertLessEqual(result["security_score"], 40)

    def test_unverified_email_is_critical(self):
        result = evaluate_profile_security(
            {
                "mfa_enabled": True,
                "email_verified": False,
                "has_email": True,
                "password_expired": False,
                "password_strength_ok": True,
                "has_passkey": False,
                "has_recovery": False,
                "phone_verified": False,
                "session_count_high": False,
                "profile": {
                    "has_photo": True,
                    "has_first_name": True,
                    "has_last_name": True,
                    "has_phone": False,
                },
            }
        )
        threats = [v["threat"] for v in result["critical_vulnerabilities"]]
        self.assertTrue(any("email" in t.lower() for t in threats))

    def test_profile_completeness_independent_of_security(self):
        result = evaluate_profile_security(
            {
                "mfa_enabled": False,
                "email_verified": False,
                "has_email": True,
                "password_expired": True,
                "password_strength_ok": False,
                "has_passkey": False,
                "has_recovery": False,
                "phone_verified": False,
                "session_count_high": False,
                "profile": {
                    "has_photo": True,
                    "has_first_name": True,
                    "has_last_name": True,
                    "has_phone": True,
                },
            }
        )
        self.assertGreaterEqual(result["profile_completeness"], 75)
        self.assertLessEqual(result["security_score"], 40)

    def test_strength_bands(self):
        self.assertEqual(strength_band(20), "weak")
        self.assertEqual(strength_band(55), "average")
        self.assertEqual(strength_band(90), "strong")

    def test_unauthenticated_user_scores_at_risk(self):
        user = User()
        user.is_active = False
        result = evaluate_user_profile_security(user)
        self.assertLessEqual(result["security_score"], 40)
        self.assertGreater(len(result["critical_vulnerabilities"]), 0)
