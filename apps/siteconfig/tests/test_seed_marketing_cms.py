from django.core.management import call_command
from django.test import TestCase

from apps.siteconfig.models_marketing import BlogPost, MarketingContent


class SeedMarketingCmsTests(TestCase):
    def test_seed_is_idempotent_and_creates_posts(self):
        call_command("seed_marketing_cms", verbosity=0)
        self.assertGreaterEqual(BlogPost.objects.filter(is_published=True).count(), 4)
        self.assertTrue(
            MarketingContent.objects.filter(key="landing_hero_headline").exists()
        )
        call_command("seed_marketing_cms", verbosity=0)
        self.assertGreaterEqual(BlogPost.objects.filter(is_published=True).count(), 4)
