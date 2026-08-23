"""A help centre written in the school's own language must survive its second article.

The KB slug columns are ``blank=True`` AND ``unique=True``. Blank stores "" rather than
NULL, and both Postgres and SQLite treat "" as an ordinary value under a unique index, so
only ONE row may hold it -- the same shape that made ``School.subdomain`` optional exactly
once (schools.0087).

What put a row there was ``slugify``. It drops every character it cannot transliterate, so
``slugify("教育")`` and ``slugify("التعليم")`` are both "" -- and the KB models assigned
that result unguarded. The first non-Latin article saved; the second raised IntegrityError.

RunMyCampus ships 17 locales including Arabic, so this is the ordinary case for a school
that writes its help centre in its own language, not an exotic edge. The sibling forum
models already carried an ``or "topic"`` fallback; the KB models never got one.

A fallback alone is not enough, which is what the collision tests below are for: if every
Arabic article falls back to "article", the second one collides on THAT instead.
"""
from __future__ import annotations

from django.test import TestCase
from django.utils.text import slugify

from apps.portal.models_kb import FAQCategory, KBArticle, KBCategory

CHINESE = "教育"
ARABIC = "التعليم"
AMHARIC = "ትምህርት"


class SlugifyPremiseTests(TestCase):
    """Pin the behaviour the whole bug rests on, so this file explains itself later."""

    def test_slugify_returns_empty_for_non_latin_scripts(self):
        self.assertEqual(slugify(CHINESE), "")
        self.assertEqual(slugify(ARABIC), "")
        self.assertEqual(slugify(AMHARIC), "")

    def test_slugify_is_fine_for_latin(self):
        """Calibration: the helper must not be papering over a broken slugify."""
        self.assertEqual(slugify("Fees & Billing"), "fees-billing")


class FAQCategorySlugTests(TestCase):
    def test_a_non_latin_category_gets_a_usable_slug(self):
        category = FAQCategory.objects.create(name=CHINESE)
        self.assertTrue(category.slug, "a category was saved with an empty slug")

    def test_two_non_latin_categories_can_coexist(self):
        first = FAQCategory.objects.create(name=CHINESE)
        second = FAQCategory.objects.create(name=ARABIC)
        self.assertNotEqual(first.slug, second.slug)

    def test_three_non_latin_categories_keep_diverging(self):
        """Two could be a fluke of the first fallback; three exercises the counter."""
        slugs = {
            FAQCategory.objects.create(name=name).slug
            for name in (CHINESE, ARABIC, AMHARIC)
        }
        self.assertEqual(len(slugs), 3, f"slugs collapsed: {slugs}")

    def test_a_latin_name_still_gets_the_readable_slug(self):
        category = FAQCategory.objects.create(name="Fees and Billing")
        self.assertEqual(category.slug, "fees-and-billing")

    def test_an_explicit_slug_is_never_overwritten(self):
        category = FAQCategory.objects.create(name="Anything", slug="chosen-by-hand")
        self.assertEqual(category.slug, "chosen-by-hand")

    def test_two_names_that_slugify_the_same_do_not_collide(self):
        """The collision path is not exclusive to non-Latin names.

        `name` is itself unique, so the two categories must differ by name while
        slugifying identically -- punctuation is dropped, so these both want
        "fees-billing".
        """
        first = FAQCategory.objects.create(name="Fees & Billing")
        second = FAQCategory.objects.create(name="Fees  Billing")
        self.assertEqual(first.slug, "fees-billing")
        self.assertNotEqual(first.slug, second.slug)
        self.assertTrue(second.slug.startswith("fees-billing"))

    def test_resaving_a_category_does_not_change_its_slug(self):
        """A slug that moves on save breaks every link already published to it."""
        category = FAQCategory.objects.create(name="Transport")
        original = category.slug
        category.name = "Transport and Buses"
        category.save()
        category.refresh_from_db()
        self.assertEqual(category.slug, original)


class KBCategorySlugTests(TestCase):
    def test_two_non_latin_categories_can_coexist(self):
        first = KBCategory.objects.create(name=CHINESE)
        second = KBCategory.objects.create(name=ARABIC)
        self.assertTrue(first.slug)
        self.assertNotEqual(first.slug, second.slug)


class KBArticleSlugTests(TestCase):
    def setUp(self):
        super().setUp()
        self.category = KBCategory.objects.create(name="General")

    def _article(self, title):
        return KBArticle.objects.create(
            title=title,
            category=self.category,
            summary="s",
            content="c",
        )

    def test_a_non_latin_article_gets_a_usable_slug(self):
        self.assertTrue(self._article(ARABIC).slug)

    def test_two_non_latin_articles_can_coexist(self):
        """The exact failure: a school writing its second article in Arabic."""
        first = self._article(ARABIC)
        second = self._article(CHINESE)
        self.assertNotEqual(first.slug, second.slug)

    def test_a_latin_article_keeps_its_readable_slug(self):
        self.assertEqual(self._article("How To Pay Fees").slug, "how-to-pay-fees")

    def test_the_slug_never_exceeds_the_column(self):
        """The counter suffix must fit INSIDE max_length, not push past it."""
        long_title = "a" * 400
        first = self._article(long_title)
        second = self._article(long_title)
        for article in (first, second):
            self.assertLessEqual(len(article.slug), 200)
        self.assertNotEqual(first.slug, second.slug)
