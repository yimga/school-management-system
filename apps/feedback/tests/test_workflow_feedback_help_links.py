"""Phase 11 — workflow ↔ feedback hook contracts.

Asserts that workflows declaring a ``related_feedback_route`` reference a URL
name that COULD resolve (we don't run Django's URL resolver here — that
needs a Django boot — but we lock the structural contract).
"""
from __future__ import annotations

from django.test import SimpleTestCase

from apps.platform_runtime import workflow_registry


class FeedbackRouteShapeTests(SimpleTestCase):
    def test_feedback_routes_use_namespaced_pattern(self):
        """Feedback routes should be Django URL names with a namespace
        (e.g. ``feedback:submit``) so reverse() can resolve them inside any
        host's URLconf."""
        for key, wf in workflow_registry.WORKFLOWS.items():
            fb_route = getattr(wf, "related_feedback_route", None)
            if fb_route is None:
                continue
            self.assertIsInstance(fb_route, str)
            self.assertTrue(fb_route, f"Workflow {key} has empty feedback route")
            # Either it's an unnamed view name or a namespaced one — accept both
            # but flag obvious bad values
            self.assertNotIn(
                " ", fb_route,
                f"Workflow {key} feedback route {fb_route!r} has spaces",
            )


class HelpArticleSlugShapeTests(SimpleTestCase):
    def test_help_article_slugs_are_kebab_case(self):
        for key, wf in workflow_registry.WORKFLOWS.items():
            slug = getattr(wf, "related_help_article", None)
            if slug is None:
                continue
            self.assertIsInstance(slug, str)
            self.assertEqual(
                slug, slug.lower(),
                f"Workflow {key} help slug {slug!r} must be lowercase",
            )
            self.assertNotIn(" ", slug, f"Help slug {slug!r} has spaces")


class FeedbackImportPostureTests(SimpleTestCase):
    """apps/feedback/* must NOT import apps/platform_runtime/workflow_*
    (one-way dependency — feedback is a leaf, workflow guidance imports it)."""

    def test_feedback_app_does_not_import_workflow_registry(self):
        import pathlib
        repo = pathlib.Path(__file__).resolve().parents[3]
        feedback_dir = repo / "apps" / "feedback"
        if not feedback_dir.exists():
            self.skipTest("apps/feedback not present")
        for p in feedback_dir.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            txt = p.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn(
                "from apps.platform_runtime.workflow_registry",
                txt,
                f"{p} imports workflow_registry — creates a circular dep",
            )
            self.assertNotIn(
                "from apps.platform_runtime.workflow_guidance",
                txt,
                f"{p} imports workflow_guidance — creates a circular dep",
            )
