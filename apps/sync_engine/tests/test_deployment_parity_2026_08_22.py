"""Cloud/box parity: what must match, what may differ, and what must NOT match.

The last class is the one a naive "make them identical" reading gets wrong. A box
lives in a school office and can be carried out of it; if its SECRET_KEY equals the
cloud's, a stolen box is a stolen cloud. Equality there is the finding.
"""
from django.test import SimpleTestCase, override_settings

from apps.sync_engine.deployment_parity import (
    MAY_DIFFER,
    MUST_DIFFER,
    MUST_MATCH,
    UNCLASSIFIED,
    classify,
    compare,
    local_fingerprint,
)


class ClassificationTests(SimpleTestCase):
    def test_code_identity_must_match(self):
        self.assertEqual(classify("APP_VERSION"), MUST_MATCH)

    def test_network_identity_may_differ(self):
        self.assertEqual(classify("ALLOWED_HOSTS"), MAY_DIFFER)

    def test_lan_http_cookie_switches_may_differ(self):
        # A plain-HTTP LAN box MUST turn these off or login silently bounces.
        for name in ("SESSION_COOKIE_SECURE", "SECURE_SSL_REDIRECT", "SECURE_HSTS_SECONDS"):
            self.assertEqual(classify(name), MAY_DIFFER, name)

    def test_secrets_must_differ(self):
        self.assertEqual(classify("SECRET_KEY"), MUST_DIFFER)

    def test_unknown_setting_is_not_silently_assumed_safe(self):
        self.assertEqual(classify("SOME_SETTING_NOBODY_CLASSIFIED"), UNCLASSIFIED)


class FingerprintTests(SimpleTestCase):
    def test_reports_code_schema_and_assets(self):
        fingerprint = local_fingerprint().as_dict()
        self.assertIn("commit_sha", fingerprint["code"])
        self.assertIn("app_version", fingerprint["code"])
        self.assertIn("schema", fingerprint)

    @override_settings(SECRET_KEY="a-very-secret-value-nobody-should-see")
    def test_secret_values_are_never_in_the_report(self):
        fingerprint = local_fingerprint().as_dict()
        self.assertNotIn(
            "a-very-secret-value-nobody-should-see", repr(fingerprint)
        )
        # ...but it IS reported, as a digest, so a collision can still be detected.
        self.assertTrue(fingerprint["settings"]["SECRET_KEY"])


class CompareTests(SimpleTestCase):
    def _fp(self, secret="s1", **over):
        base = {
            "code": {"commit_sha": "aaa", "app_version": "1.0", "environment": "cloud"},
            "assets": {"service_worker_cache_version": "sms-v1"},
            "schema": {"available": True, "total": 10, "digest": "d1"},
            "settings": {"APP_VERSION": "x", "SECRET_KEY": secret, "TIME_ZONE": "t1"},
        }
        base.update(over)
        return base

    def _remote(self, **over):
        """The other side. Distinct SECRET_KEY, because a shared one is a finding."""
        return self._fp(secret="s2", **over)

    def test_same_commit_is_not_drift(self):
        findings = compare(self._fp(), self._remote())
        self.assertEqual([f for f in findings if f.is_defect], [])

    def test_different_commit_is_drift(self):
        remote = self._remote(code={"commit_sha": "bbb", "app_version": "1.0", "environment": "edge"})
        drift = [f for f in compare(self._fp(), remote) if f.is_defect]
        self.assertEqual([f.key for f in drift], ["commit_sha"])

    def test_environment_difference_is_expected_not_drift(self):
        remote = self._remote(code={"commit_sha": "aaa", "app_version": "1.0", "environment": "edge"})
        verdicts = {f.key: f.verdict for f in compare(self._fp(), remote)}
        self.assertEqual(verdicts["environment"], "EXPECTED")

    def test_different_migration_set_is_drift(self):
        remote = self._remote(schema={"available": True, "total": 9, "digest": "d2"})
        drift = [f for f in compare(self._fp(), remote) if f.is_defect]
        self.assertIn("applied_migrations", [f.key for f in drift])

    def test_timezone_difference_is_not_a_defect(self):
        remote = self._fp(settings={"APP_VERSION": "x", "SECRET_KEY": "s2", "TIME_ZONE": "t2"})
        drift = [f for f in compare(self._fp(), remote) if f.is_defect]
        self.assertEqual(drift, [])

    def test_shared_secret_is_a_collision(self):
        # Both sides carrying the SAME SECRET_KEY digest is the security finding.
        remote = self._fp(settings={"APP_VERSION": "x", "SECRET_KEY": "s1", "TIME_ZONE": "t2"})
        local = self._fp(settings={"APP_VERSION": "x", "SECRET_KEY": "s1", "TIME_ZONE": "t1"})
        collisions = [f for f in compare(local, remote) if f.verdict == "COLLISION"]
        self.assertEqual([f.key for f in collisions], ["SECRET_KEY"])

    def test_different_secrets_are_correct_and_silent(self):
        remote = self._fp(settings={"APP_VERSION": "x", "SECRET_KEY": "s2", "TIME_ZONE": "t1"})
        self.assertEqual([f for f in compare(self._fp(), remote) if f.is_defect], [])

    def test_must_match_setting_that_differs_is_drift(self):
        remote = self._fp(settings={"APP_VERSION": "y", "SECRET_KEY": "s2", "TIME_ZONE": "t1"})
        drift = [f for f in compare(self._fp(), remote) if f.is_defect]
        self.assertEqual([f.key for f in drift], ["APP_VERSION"])

    def test_unreported_schema_is_unknown_not_agreement(self):
        remote = self._remote(schema={})
        verdicts = [f.verdict for f in compare(self._fp(), remote) if f.key == "applied_migrations"]
        self.assertEqual(verdicts, ["UNKNOWN"])
