from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.finance.views import _backend_flags


class FinanceHardeningHelperTests(SimpleTestCase):
    def test_backend_flags_returns_empty_dict_when_runtime_lookup_fails(self):
        request = RequestFactory().get("/finance/")

        with patch("apps.finance.views.get_effective_flags", side_effect=RuntimeError("runtime unavailable")):
            self.assertEqual(_backend_flags(request), {})
