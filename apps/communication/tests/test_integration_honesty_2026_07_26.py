"""Integration surfaces must not (a) silently persist plaintext credentials or
(b) hand users a fabricated meeting link that does not resolve.

(a) ServiceIntegration.save() Fernet-wraps secret-named config keys; if encryption
    genuinely fails, a secret would persist as PLAINTEXT (a DB/backup leak — Audit
    C1). ``config_has_plaintext_secret`` is the fail-closed detector.
(b) Google Meet has no live Calendar-API path yet; it used to fabricate a
    ``meet.google.com/<random>`` URL that 404s. It now falls back to a REAL Jitsi
    room, tagged with the true provider.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.communication.secret_config import (
    ENC_PREFIX,
    config_has_plaintext_secret,
    encrypt_config,
)
from apps.communication.video_conferencing import (
    VideoConferenceProvider,
    VideoConferenceService,
)


class PlaintextSecretGuardTests(SimpleTestCase):
    def test_plaintext_secret_is_detected(self):
        self.assertTrue(config_has_plaintext_secret({"access_token": "raw-token"}))
        self.assertTrue(config_has_plaintext_secret({"api_secret": "s3cr3t"}))

    def test_encrypted_secret_is_not_flagged(self):
        self.assertFalse(
            config_has_plaintext_secret({"access_token": ENC_PREFIX + "abc"})
        )

    def test_non_secret_keys_are_ignored(self):
        self.assertFalse(config_has_plaintext_secret({"campus_id": "5", "scope": "read"}))

    def test_encrypt_config_then_detector_is_clean(self):
        # The real path: after encrypt_config wraps the token, no plaintext remains.
        encrypted = encrypt_config({"access_token": "live-token-value"})
        self.assertFalse(config_has_plaintext_secret(encrypted))


class GoogleMeetHonestyTests(SimpleTestCase):
    def test_google_meet_falls_back_to_real_jitsi_not_fabricated_link(self):
        svc = VideoConferenceService(provider=VideoConferenceProvider.GOOGLE_MEET)
        host = SimpleNamespace(email="teacher@example.com", id=1, username="teacher")
        result = svc.create_meeting(host, "Parent Conference", datetime(2026, 1, 1, 10, 0), 30)
        join = str(result.get("join_url") or "")
        self.assertTrue(join)
        # The old bug: a fabricated meet.google.com link that never resolves.
        self.assertNotIn("meet.google.com", join)
        self.assertEqual(result.get("provider"), "jitsi")
        self.assertEqual(result.get("requested_provider"), "google_meet")
        self.assertEqual(
            result.get("provider_fallback_reason"), "google_meet_live_api_not_configured"
        )
