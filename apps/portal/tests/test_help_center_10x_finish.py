"""Help center 10x finish — auto-draft HITL publish + production default (batch 1485–1486)."""

from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings

from apps.feedback.models import HelpContentGapTask
from apps.portal.help_content_gaps import ensure_content_gap_task
from apps.portal.kb_hitl_publish import publish_kb_article
from apps.portal.models_kb import KBCategory


class AutoDraftHitlPublishTests(TestCase):
    def setUp(self):
        self.category = KBCategory.objects.create(
            slug="test-gap-category",
            name="Test",
            description="",
            icon="bi-journal-text",
            display_order=1,
        )

    @override_settings(
        HELP_ZERO_RESULT_AUTO_DRAFT_KB=True,
        HELP_ZERO_RESULT_AUTO_DRAFT_HITS=3,
        KB_EMBEDDING_AUTO_REFRESH=False,
    )
    def test_gap_auto_draft_then_hitl_publish(self):
        task = ensure_content_gap_task(fingerprint="abc123deadbeef", increment=3)
        task.refresh_from_db()
        self.assertEqual(task.status, HelpContentGapTask.Status.DRAFTED)
        self.assertIsNotNone(task.kb_draft_article_id)
        article = task.kb_draft_article
        self.assertEqual(article.status, "DRAFT")
        publish_kb_article(article)
        article.refresh_from_db()
        self.assertEqual(article.status, "PUBLISHED")
        self.assertIsNotNone(article.published_at)


class AutoDraftProductionDefaultTests(TestCase):
    def test_settings_declares_staging_prod_auto_draft_default(self):
        settings_path = Path(settings.BASE_DIR) / "config" / "settings.py"
        text = settings_path.read_text(encoding="utf-8")
        self.assertIn("_HELP_AUTO_DRAFT_DEFAULT", text)
        self.assertIn("_IS_PRODUCTION_OR_STAGING", text)
        self.assertIn('HELP_ZERO_RESULT_AUTO_DRAFT_KB = os.getenv', text)
