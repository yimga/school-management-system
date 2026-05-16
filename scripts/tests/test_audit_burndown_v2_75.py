"""Regression: Wave 4 (v2.75) burndown — audits must stay at zero.

Closes:
  - audit_no_placeholder: 2 -> 0  (sample-data wording on 2 templates)
  - audit_page_standards: 6 -> 0  (inline <script> on 6 templates moved to external)
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def _run_audit(script: str, json_arg: bool = False, json_out: Path | None = None) -> dict:
    cmd = [sys.executable, "-X", "utf8", f"scripts/{script}"]
    if json_arg and json_out is not None:
        cmd.extend(["--json", str(json_out)])
    subprocess.run(cmd, cwd=REPO, check=True, capture_output=True)
    return {}


class WaveAuditBurndownTests(unittest.TestCase):
    def test_no_placeholder_audit_clean(self):
        _run_audit("audit_no_placeholder.py")
        data = json.loads(
            (REPO / "docs/generated/no_placeholder_audit.json").read_text(encoding="utf-8")
        )
        findings = data.get("findings") if isinstance(data, dict) else data
        self.assertEqual(
            len(findings or []),
            0,
            f"audit_no_placeholder must stay at 0 — got {findings!r}",
        )

    def test_page_standards_audit_clean(self):
        json_out = REPO / ".tmp_test_artifacts" / "page_standards.json"
        json_out.parent.mkdir(parents=True, exist_ok=True)
        _run_audit("audit_page_standards.py", json_arg=True, json_out=json_out)
        data = json.loads(json_out.read_text(encoding="utf-8"))
        rows = data.get("rows") or data.get("findings") or []
        offenders = [r for r in rows if r.get("findings")]
        self.assertEqual(
            offenders,
            [],
            f"audit_page_standards must stay at 0 — found {len(offenders)} offending templates",
        )


if __name__ == "__main__":
    unittest.main()
