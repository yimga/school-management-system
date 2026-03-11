from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from apps.api import search_read_layer


class SearchReadLayerHelperTests(SimpleTestCase):
    @override_settings(OPENSEARCH_DSN="https://search.example.test")
    def test_search_returns_none_when_opensearch_backend_fails(self):
        with patch("apps.api.search_read_layer.OPENSEARCH_DSN", "https://search.example.test"):
            with patch("apps.api.search_read_layer._opensearch_available", return_value=True):
                with patch("apps.api.search_read_layer._search_opensearch", side_effect=RuntimeError("down")):
                    self.assertIsNone(search_read_layer.search("term"))
