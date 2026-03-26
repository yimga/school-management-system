from pathlib import Path

from django.test import SimpleTestCase


class OpenSourceAIEnforcementTests(SimpleTestCase):
    def test_apps_do_not_import_forbidden_cloud_ai_sdks(self):
        repo_root = Path(__file__).resolve().parents[2]
        apps_root = repo_root / "apps"
        forbidden = (
            "google.generativeai",
            "generativelanguage.googleapis.com",
            "anthropic",
            "openai.OpenAI(",
        )
        violations: list[str] = []
        for path in apps_root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in forbidden:
                if needle in text:
                    violations.append(f"{path}: {needle}")
        self.assertEqual(violations, [], "\n".join(violations))
