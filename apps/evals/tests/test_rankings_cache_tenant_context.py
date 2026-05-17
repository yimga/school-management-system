"""Rankings cache TTL reads tenant-scoped effective settings (RLS batch 1265)."""

from unittest.mock import patch

from django.test import TestCase, tag

from apps.evals.caching import get_rankings


@tag("tenants_rls")
class RankingsCacheTenantContextTests(TestCase):
    @patch("apps.evals.caching.cache.set")
    @patch("apps.evals.caching.cache.get", return_value=None)
    @patch("apps.automation.helpers.get_cached_site_settings")
    def test_rankings_cache_uses_effective_settings_ttl(
        self, mock_get_settings, _mock_cache_get, mock_cache_set
    ):
        settings = type(
            "EffSettings",
            (),
            {"cache_rankings_interval_minutes": 33},
        )()
        mock_get_settings.return_value = settings

        with patch("apps.evals.caching.Evaluation.objects") as mock_eval:
            mock_eval.filter.return_value.values.return_value.annotate.return_value.order_by.return_value = []
            get_rankings(year_id=1, term_id=1)

        mock_get_settings.assert_called()
        mock_cache_set.assert_called()
        args, _kwargs = mock_cache_set.call_args
        ttl_seconds = args[2] if len(args) > 2 else _kwargs.get("timeout")
        self.assertEqual(ttl_seconds, 33 * 60)
