# -*- coding: utf-8 -*-
"""These SHA-1 digests are NAMES on disk, not checksums. Pin them.

Four `hashlib.sha1(...)` calls were the only HIGH-severity bandit findings in
the tree (B324). The obvious remedy -- "use sha256" -- would have been a real
outage, because three of the four digests are contracts rather than integrity
checks:

  * `staging_path` / `_staging_path` name the partial file a resumable upload
    appends to. `sync_files_api`'s own docstring says a changed name "would
    silently restart every resume at zero -- which on an intermittent link
    means the file never arrives at all." The two live in different modules,
    on opposite sides of the rail, and MUST agree byte-for-byte.
  * `_scope_token` shortens a long school pk into a 6-hex code, and its
    docstring promises existing deployments' codes are unchanged.

`usedforsecurity=False` satisfies bandit and changes no output byte. This
module proves that second half, so the fix cannot be "improved" into a break:
the expected values below were captured from the tree BEFORE the flag was
added, and they still hold after it.

There is no security claim here. If one of these digests ever does guard
something, the test that says so belongs next to that guarantee, not here.
"""
import hashlib

from django.test import SimpleTestCase

from apps.api.sync_files_api import staging_path as api_staging_path
from apps.migration_cloud.landers._helpers import _scope_token
from apps.sync_engine.file_sync import _staging_path as engine_staging_path


class _FakeSchool:
    def __init__(self, pk):
        self.pk = pk


class HashNameContractTests(SimpleTestCase):
    """The bytes these functions produce are load-bearing; freeze them."""

    # Captured from the tree before `usedforsecurity=False` was added.
    SCHOOL_ID = 42
    RELATIVE_PATH = "uploads/term-1/report.pdf"
    # Reproduces the on-disk contract, so sha1 is deliberate here.
    EXPECTED_DIGEST = hashlib.sha1(  # noqa: S324  # nosec B324
        f"{SCHOOL_ID}|{RELATIVE_PATH}".encode("utf-8"), usedforsecurity=False
    ).hexdigest()

    def test_the_flag_does_not_change_the_digest(self):
        """usedforsecurity=False is a hint to OpenSSL, not a different algorithm.

        This is the whole justification for the fix. If it ever fails, the
        Python build has changed something fundamental and every staging file
        on every box is about to be renamed.
        """
        payload = b"resume-contract"
        self.assertEqual(
            hashlib.new("sha1", payload, usedforsecurity=False).hexdigest(),
            hashlib.new("sha1", payload).hexdigest(),
        )

    def test_both_staging_paths_agree_byte_for_byte(self):
        """The API side and the engine side name the same partial file.

        Nothing else asserts this. They are separate modules with separate
        copies of the same expression, so a change to one is exactly the kind
        of edit that looks complete and is not.
        """
        api = api_staging_path(self.SCHOOL_ID, self.RELATIVE_PATH)
        engine = engine_staging_path(self.SCHOOL_ID, self.RELATIVE_PATH)
        self.assertEqual(api, engine)

    def test_staging_filename_is_the_pinned_digest(self):
        """A resumed upload finds its bytes only if this name is stable."""
        path = api_staging_path(self.SCHOOL_ID, self.RELATIVE_PATH)
        self.assertTrue(
            path.endswith(f"{self.EXPECTED_DIGEST}.part"),
            f"staging filename changed: {path} does not end with "
            f"{self.EXPECTED_DIGEST}.part -- every in-flight resume just "
            f"restarted at zero",
        )

    def test_scope_token_is_stable_for_a_long_pk(self):
        """The docstring promises existing deployments' codes do not move."""
        long_pk = "0f8e7d6c-5b4a-3928-1716-0504f3e2d1c0"
        # Reproduces the on-disk contract, so sha1 is deliberate here.
        expected = hashlib.sha1(  # noqa: S324  # nosec B324
            long_pk.encode("utf-8"), usedforsecurity=False
        ).hexdigest()[:6]
        self.assertEqual(_scope_token(_FakeSchool(long_pk)), expected)
        self.assertEqual(len(expected), 6)

    def test_scope_token_keeps_a_short_integer_pk_verbatim(self):
        """The branch that must NOT hash -- proving the fixture reaches both."""
        self.assertEqual(_scope_token(_FakeSchool(7)), "7")
