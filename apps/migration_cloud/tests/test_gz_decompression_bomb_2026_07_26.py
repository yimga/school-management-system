"""Archive intake must refuse a gzip decompression bomb instead of OOM-ing.

``_iter_archive_members`` used to ``gz.read()`` a single-file ``.gz`` with no
ceiling — gzip's uncompressed size is unknown until read, so a few-KB file could
inflate to many GB and kill the worker BEFORE the per-artifact byte cap (checked
only on the yielded, already-inflated size) ever ran. The read is now bounded to
cap+1 bytes and refuses anything over the cap.
"""

from __future__ import annotations

import gzip
import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.migration_cloud.intake.archive_intake import _iter_archive_members
from apps.migration_cloud.intake.base import IntakeError


class GzBombGuardTests(SimpleTestCase):
    def _write_gz(self, tmpdir, name, payload):
        p = Path(tmpdir) / name
        with gzip.open(p, "wb") as gz:
            gz.write(payload)
        return p

    def test_gz_over_cap_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_gz(td, "big.csv.gz", b"x" * 5000)
            with self.assertRaises(IntakeError):
                # cap far below the decompressed size -> refuse (bomb-shaped)
                list(_iter_archive_members(p, max_bytes=100))

    def test_gz_within_cap_yields_member(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_gz(td, "ok.csv.gz", b"a,b\n1,2\n")
            members = list(_iter_archive_members(p, max_bytes=1_000_000))
            self.assertEqual(len(members), 1)
            member_name, opener, declared = members[0]
            self.assertEqual(member_name, "ok.csv")
            self.assertEqual(declared, len(b"a,b\n1,2\n"))
            with opener() as stream:
                self.assertEqual(stream.read(), b"a,b\n1,2\n")
