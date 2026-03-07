from django.test import TestCase

from apps.siteconfig.models import ReportCardStyle


class ReportCardStyleCatalogSeedTests(TestCase):
    def test_seeded_catalog_contains_expected_distinct_styles(self):
        expected_slugs = {
            "classic",
            "cameroon-letterhead",
            "academic-authority",
            "digital-lavender",
            "modern-sage",
            "midnight-scholar",
            "sunrise-ledger",
            "eco-digital",
            "neo-brutalist",
            "monochrome-pro",
            "bento-schoolboard",
            "heritage-scholar",
        }
        seeded_slugs = set(ReportCardStyle.objects.values_list("slug", flat=True))
        self.assertTrue(expected_slugs.issubset(seeded_slugs))
