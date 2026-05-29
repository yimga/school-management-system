from django.core.management import call_command
from django.test import TestCase

from apps.schools.marketing_content_seed import (
    marketing_content_dir,
    validate_marketing_content_json_files,
)
from apps.siteconfig.models_marketing import BlogPost, MarketingContent


class SeedMarketingSiteTests(TestCase):
    def test_seed_marketing_site_is_idempotent(self):
        call_command(
            "seed_marketing_site",
            skip_loops=True,
            skip_fr_translations=True,
            verbosity=0,
        )
        self.assertGreaterEqual(BlogPost.objects.filter(is_published=True).count(), 4)
        self.assertTrue(
            MarketingContent.objects.filter(key="landing_hero_headline").exists()
        )
        self.assertFalse(validate_marketing_content_json_files())
        json_count = len(list(marketing_content_dir().glob("*.json")))
        self.assertGreaterEqual(json_count, 80)

        call_command(
            "seed_marketing_site",
            skip_loops=True,
            skip_fr_translations=True,
            verbosity=0,
        )
        self.assertEqual(
            len(list(marketing_content_dir().glob("*.json"))),
            json_count,
        )
