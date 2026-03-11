from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase

from apps.siteconfig.context_processors import _resolve_backend_feature_flags


class ContextProcessorRuntimeFlagsTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_resolve_backend_feature_flags_prefers_runtime_helper(self):
        request = self.factory.get("/")
        site = SimpleNamespace(backend_feature_flags={"legacy_flag": False})

        with patch(
            "apps.siteconfig.context_processors.get_effective_flags",
            return_value={"runtime_flag": True},
        ):
            flags = _resolve_backend_feature_flags(request, site)

        self.assertEqual(flags, {"runtime_flag": True})

    def test_resolve_backend_feature_flags_falls_back_to_site_when_runtime_helper_fails(self):
        request = self.factory.get("/")
        site = SimpleNamespace(backend_feature_flags={"legacy_flag": True})

        with patch(
            "apps.siteconfig.context_processors.get_effective_flags",
            side_effect=AttributeError,
        ):
            flags = _resolve_backend_feature_flags(request, site)

        self.assertEqual(flags, {"legacy_flag": True})

    def test_resolve_backend_feature_flags_uses_owner_aware_site_accessor_when_available(self):
        request = self.factory.get("/")

        class _Site:
            def get_backend_feature_flags(self):
                return {"owner_flag": True}

        with patch(
            "apps.siteconfig.context_processors.get_effective_flags",
            side_effect=AttributeError,
        ):
            flags = _resolve_backend_feature_flags(request, _Site())

        self.assertEqual(flags, {"owner_flag": True})
