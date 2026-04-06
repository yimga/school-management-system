from pathlib import Path

from django.test import SimpleTestCase


class OpenSourceAIEnforcementTests(SimpleTestCase):
    def test_product_code_does_not_import_forbidden_cloud_ai_sdks(self):
        repo_root = Path(__file__).resolve().parents[2]
        scan_roots = (repo_root / "apps", repo_root / "services")
        forbidden = (
            "google.generativeai",
            "generativelanguage.googleapis.com",
            "anthropic",
            "openai.OpenAI(",
            "from openai import OpenAI",
        )
        violations: list[str] = []
        for scan_root in scan_roots:
            if not scan_root.is_dir():
                continue
            for path in scan_root.rglob("*.py"):
                rel = path.relative_to(repo_root)
                if "tests" in rel.parts:
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore")
                for needle in forbidden:
                    if needle in text:
                        violations.append(f"{rel}: {needle}")
        self.assertEqual(violations, [], "\n".join(violations))
