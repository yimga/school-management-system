"""AST scan: wizard layer MUST NOT import services.ai_gateway directly.

Re-enforces ``scan_ai_gateway_boundary.py`` baseline 0 for the wizard layer.
"""

import ast
from pathlib import Path

from django.test import SimpleTestCase


WIZARD_LAYER_DIR = Path(__file__).resolve().parent.parent


class AIBoundaryTests(SimpleTestCase):
    def _wizard_layer_files(self):
        return [
            p for p in WIZARD_LAYER_DIR.glob("wizard*.py")
        ] + [
            p for p in WIZARD_LAYER_DIR.glob("ai_*.py")
        ]

    def test_no_direct_ai_gateway_import_in_wizard_layer(self):
        offenders = []
        for path in self._wizard_layer_files():
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.startswith("services.ai_gateway"):
                            offenders.append(f"{path.name}: import {alias.name}")
                if isinstance(node, ast.ImportFrom):
                    if node.module and node.module.startswith("services.ai_gateway"):
                        offenders.append(f"{path.name}: from {node.module}")
        # wizard_ai.py is allowed to call services.ai_helpers which re-exports TaskType,
        # but never services.ai_gateway directly.
        self.assertEqual(offenders, [], f"AI gateway boundary violated: {offenders}")

    def test_ai_helpers_is_the_only_path(self):
        wizard_ai = WIZARD_LAYER_DIR / "wizard_ai.py"
        src = wizard_ai.read_text(encoding="utf-8")
        self.assertIn("from services.ai_helpers import", src)
