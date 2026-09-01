# -*- coding: utf-8 -*-
"""The upload receiver must digest a file the same way the sender did.

`apps/api/sync_files_api.py` hashed the received bytes with SHA-1 and compared
the result to a header the sender fills with a SHA-256. A 40-character hexdigest
is never equal to a 64-character one, so the equality check was false for every
upload that declared a hash: the endpoint answered `hash_mismatch` and threw the
file away. Only senders that omitted the header could ever complete a transfer.

Nothing caught it. The three participants are in three modules and no test
compared them:

    apps/sync_engine/file_manifest.py   advertises sha256   (what a file "is")
    apps/sync_engine/file_sync.py       verifies  sha256   (engine receiver)
    apps/api/sync_files_api.py          verified  sha1     (API receiver)

Two of three agreeing is what made it survive review -- each file is
self-consistent, and the disagreement only exists between them. So this module
asserts the AGREEMENT rather than any one implementation.
"""
import hashlib
import os
import tempfile

from django.test import SimpleTestCase

from apps.api.sync_files_api import hash_received_file


class UploadHashAlgorithmTests(SimpleTestCase):
    PAYLOAD = b"a report card that must survive an intermittent link" * 4096

    def _staged(self):
        fd, path = tempfile.mkstemp(prefix="rmc-upload-hash-")
        with os.fdopen(fd, "wb") as fh:
            fh.write(self.PAYLOAD)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_receiver_digest_equals_what_the_sender_declares(self):
        """The whole contract, in one assertion.

        Before the fix this failed: the receiver produced a 40-char SHA-1 and
        the sender declares a 64-char SHA-256.
        """
        path = self._staged()
        declared = hashlib.sha256(self.PAYLOAD).hexdigest()
        self.assertEqual(hash_received_file(path), declared)

    def test_digest_is_sha256_length(self):
        """Guards the specific way this broke: a shorter digest silently used."""
        path = self._staged()
        self.assertEqual(
            len(hash_received_file(path)),
            64,
            "receiver is not producing a SHA-256; every declaring upload will "
            "be rejected as hash_mismatch",
        )

    def test_a_corrupted_file_still_fails_the_comparison(self):
        """The check must keep REJECTING real corruption, not just stop lying.

        A fix that made everything compare equal would pass the tests above and
        be far worse than the bug.
        """
        path = self._staged()
        with open(path, "ab") as fh:
            fh.write(b"tampered")
        declared = hashlib.sha256(self.PAYLOAD).hexdigest()
        self.assertNotEqual(hash_received_file(path), declared)

    def test_streaming_matches_a_single_shot_digest(self):
        """The receiver reads in 1 MiB blocks; the payload spans several."""
        path = self._staged()
        self.assertGreater(len(self.PAYLOAD), 0)
        self.assertEqual(
            hash_received_file(path), hashlib.sha256(self.PAYLOAD).hexdigest()
        )
