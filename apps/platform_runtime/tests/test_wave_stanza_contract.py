"""1022 + 1028: Runbook + wave module tuple stay aligned (contract test for validation stanza)."""

import sys
import unittest
from pathlib import Path


class WaveStanzaContractTests(unittest.TestCase):
    def test_runbook_lists_wave_modules_in_canonical_order(self):
        root = Path(__file__).resolve().parent.parent.parent.parent
        scripts_dir = str(root / "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from wave_shell_test_modules import (
            WAVE_SHELL_TEST_MODULES,
            wave_modules_from_runbook_path,
        )

        runbook = root / "docs" / "runbook" / "SOT_VALIDATION_STANZA.md"
        self.assertTrue(runbook.is_file(), msg=f"missing {runbook}")
        parsed = wave_modules_from_runbook_path(runbook)
        self.assertEqual(
            parsed,
            WAVE_SHELL_TEST_MODULES,
            msg=(
                "runbook bash stanza must list exactly these modules in this order; "
                f"got {parsed!r}"
            ),
        )
