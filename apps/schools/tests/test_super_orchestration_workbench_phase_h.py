"""Phase H skip-link regression for orchestration operator workbench (batch 32 #391)."""

from pathlib import Path

from django.conf import settings
from django.test import TestCase


class SuperOrchestrationWorkbenchPhaseHTests(TestCase):
    def test_skip_link_target_exists(self):
        path = (
            Path(settings.BASE_DIR)
            / "templates"
            / "orchestration"
            / "operator_workbench.html"
        )
        text = path.read_text(encoding="utf-8")
        self.assertIn('href="#orchestration-workbench-main"', text)
        self.assertIn('id="orchestration-workbench-main"', text)
