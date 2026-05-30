"""v4.00.92 — Unit tests for ``webhook_key_rotation`` (W17 module).

In-process dual-secret rotation ring. No DB writes, so SimpleTestCase.

Quality bar: never assert on raw secret values — only on (a) presence of
the staged record, (b) the resulting HMAC-SHA256 signature shape, and
(c) the rotation_summary's URL-leak-safe counts.
"""

from __future__ import annotations

import hashlib
import hmac

from django.test import SimpleTestCase

from apps.integrations_marketplace import webhook_key_rotation as _wkr


class WebhookKeyRotationTests(SimpleTestCase):

    def setUp(self):
        _wkr.reset_staged_secrets()

    def tearDown(self):
        _wkr.reset_staged_secrets()

    def test_stage_new_secret_respects_cap_100(self):
        """Cap is 100 — adding the 101st evicts the oldest entry."""
        # Stage 100 distinct subscriptions.
        for sub_id in range(1, 101):
            self.assertTrue(_wkr.stage_new_secret(
                subscription_id=sub_id,
                new_secret=f"secret-{sub_id}",
                grace_seconds=86400,
            ))
        summary = _wkr.rotation_summary()
        self.assertEqual(summary["staged_count"], 100)
        # The 101st pushes total back to 100 (cap honored; oldest evicted).
        self.assertTrue(_wkr.stage_new_secret(
            subscription_id=999,
            new_secret="secret-999",
            grace_seconds=86400,
        ))
        summary = _wkr.rotation_summary()
        self.assertEqual(summary["staged_count"], 100)
        # New subscription_id is present, oldest (1) was evicted.
        self.assertIn(999, summary["subscription_ids_with_staged"])
        self.assertNotIn(1, summary["subscription_ids_with_staged"])

    def test_mint_dual_signature_pair_shape(self):
        """Returns sha256=<hex> shape; ``next`` is None when no stage."""
        payload = b'{"event":"test"}'
        out = _wkr.mint_dual_signature_pair(
            payload_bytes=payload,
            active_secret="active-secret",
            subscription_id=1,
        )
        # primary signature is HMAC-SHA256 of payload w/ active secret.
        expected = hmac.new(b"active-secret", payload, hashlib.sha256).hexdigest()
        self.assertEqual(out["primary"], f"sha256={expected}")
        # No staged secret -> next is None.
        self.assertIsNone(out["next"])
        # Stage a new secret and re-mint -> next populated w/ valid HMAC.
        _wkr.stage_new_secret(
            subscription_id=1, new_secret="staged-secret", grace_seconds=86400,
        )
        out2 = _wkr.mint_dual_signature_pair(
            payload_bytes=payload,
            active_secret="active-secret",
            subscription_id=1,
        )
        expected_next = hmac.new(b"staged-secret", payload, hashlib.sha256).hexdigest()
        self.assertEqual(out2["next"], f"sha256={expected_next}")
        # We DO NOT assert raw secret values appear in the result anywhere.

    def test_promote_staged_secret(self):
        """promote returns the staged secret value + clears the slot."""
        _wkr.stage_new_secret(
            subscription_id=42, new_secret="will-be-promoted",
            grace_seconds=86400,
        )
        promoted = _wkr.promote_staged_secret(42)
        self.assertEqual(promoted, "will-be-promoted")
        # After promote, no record remains.
        summary = _wkr.rotation_summary()
        self.assertNotIn(42, summary["subscription_ids_with_staged"])
        # Promote a non-staged subscription -> None.
        self.assertIsNone(_wkr.promote_staged_secret(99999))

    def test_rotation_summary_url_leak_safe(self):
        """Summary must never leak raw secret material."""
        _wkr.stage_new_secret(
            subscription_id=7, new_secret="super-secret-payload",
            grace_seconds=86400,
        )
        summary = _wkr.rotation_summary()
        # Counts + IDs only — never secret material.
        self.assertEqual(summary["staged_count"], 1)
        self.assertEqual(summary["subscription_ids_with_staged"], [7])
        # Repr should NOT contain the staged secret string.
        self.assertNotIn("super-secret-payload", repr(summary))
        # Verify the SHA-256[:12] hash isn't accidentally present either.
        secret_hash = hashlib.sha256(b"super-secret-payload").hexdigest()[:12]
        self.assertNotIn(secret_hash, repr(summary))

    def test_grace_expiry_honored(self):
        """After grace window expires, get_staged_secret_record returns None."""
        # Stage with a grace_seconds=0 path is rejected by stage_new_secret
        # (it returns False). Instead, stage with a real window, then
        # rewrite the entry's grace_until_epoch to the past to simulate
        # expiry without time.sleep.
        self.assertTrue(_wkr.stage_new_secret(
            subscription_id=11, new_secret="grace-secret", grace_seconds=60,
        ))
        # Reach into the (locked) state and backdate the grace to the past.
        with _wkr._LOCK:
            _wkr._STAGED_SECRETS[11]["grace_until_epoch"] = 0.0
        # Now the record must be evicted on read.
        rec = _wkr.get_staged_secret_record(11)
        self.assertIsNone(rec)
        # And the slot is cleared as a side effect.
        summary = _wkr.rotation_summary()
        self.assertNotIn(11, summary["subscription_ids_with_staged"])
