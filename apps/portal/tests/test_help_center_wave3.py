"""Tests for help-center batch 1354 — all-bases-covered closeout."""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.feedback.models import HelpContentGapTask, SupportAIInteractionReview
from apps.portal.help_content_gaps import ensure_content_gap_task
from apps.portal.kb_embeddings import filter_kb_queryset_by_locale_with_fallback
from apps.portal.kb_hitl_publish import publish_kb_article
from apps.portal.models_kb import KBArticle

User = get_user_model()


class HelpCenterWave3Tests(TestCase):
    def test_content_gap_task_upsert(self):
        row = ensure_content_gap_task(fingerprint="abc123def456")
        self.assertEqual(row.hit_count, 1)
        ensure_content_gap_task(fingerprint="abc123def456", increment=2)
        row.refresh_from_db()
        self.assertEqual(row.hit_count, 3)

    def test_csat_down_opens_hitl_review(self):
        user = User.objects.create_user(username="csat3", password="x")
        rf = RequestFactory()
        req = rf.post(
            "/api/ai/support-session-rating/",
            data='{"thumbs":"down","query":"billing export failed"}',
            content_type="application/json",
        )
        req.user = user
        from apps.portal.views_ai_gateway import api_support_session_rating

        view = api_support_session_rating
        while hasattr(view, "__wrapped__"):
            view = view.__wrapped__
        resp = view(req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(SupportAIInteractionReview.objects.filter(thumbs="down").count(), 1)

    def test_publish_kb_article(self):
        from apps.portal.models_kb import KBCategory

        cat = KBCategory.objects.create(name="Ops", slug="ops", is_active=True)
        art = KBArticle.objects.create(
            title="Draft",
            slug="draft-pub-test",
            category=cat,
            status="DRAFT",
        )
        publish_kb_article(art)
        art.refresh_from_db()
        self.assertEqual(art.status, "PUBLISHED")
        self.assertIsNotNone(art.published_at)

    def test_locale_fallback_queryset_runs(self):
        qs = filter_kb_queryset_by_locale_with_fallback(KBArticle.objects.all())
        self.assertIsNotNone(qs)

    @override_settings(ROOT_URLCONF="config.manager_urls")
    def test_manager_locale_families_resolves(self):
        url = reverse("manager_kb_locale_families")
        self.assertIn("locale-families", url)

    def test_resolve_journey_articles_returns_urls(self):
        from apps.portal.help_guided_journeys import resolve_journey_articles

        rows = resolve_journey_articles(school=None, path="/finance/dashboard/")
        for row in rows:
            self.assertIn("title", row)
            self.assertIn("url", row)
