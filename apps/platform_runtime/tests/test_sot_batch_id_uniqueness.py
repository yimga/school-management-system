"""Unit tests for the SOT §11.4 batch-ID uniqueness verifier."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from apps.platform_runtime.tests.support.script_loading import load_repo_script


def _load_module():
    return load_repo_script(
        "scripts/verify_sot_batch_id_uniqueness.py",
        "verify_sot_batch_id_uniqueness",
        register_in_sys_modules=True,
    )


class SotBatchIdUniquenessTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._mod = _load_module()

    def test_duplicate_batch_without_alias_fails(self):
        rows = [
            self._mod.BatchRow("1193", 10, "**§11.4 forward queue - batch 1193:** A"),
            self._mod.BatchRow("1193", 20, "**§11.4 forward queue - batch 1193:** B"),
        ]

        errors = self._mod.duplicate_errors(rows)

        self.assertEqual(len(errors), 1)
        self.assertIn("batch 1193", errors[0])

    def test_duplicate_batch_with_one_superseded_alias_passes(self):
        rows = [
            self._mod.BatchRow("1193", 10, "**§11.4 forward queue - batch 1193:** A"),
            self._mod.BatchRow(
                "1193",
                20,
                "**§11.4 forward queue - batch 1193 "
                "(superseded alias):** historical row",
            ),
        ]

        self.assertEqual(self._mod.duplicate_errors(rows), [])

    def test_parser_only_reads_forward_queue_rows(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "sot.md"
            path.write_text(
                "\n".join(
                    [
                        "# SOT",
                        "**§11.4 forward queue - batch 1200:** current",
                        "**§11.4 forward queue - batch 1170-dev:** dev row",
                        "**batch 1200:** not a forward queue row",
                        "**§11.5 forward queue - batch 1200:** not 11.4",
                    ]
                ),
                encoding="utf-8",
            )

            rows = self._mod.parse_sot_rows(path)

        self.assertEqual([row.batch_id for row in rows], ["1200"])
