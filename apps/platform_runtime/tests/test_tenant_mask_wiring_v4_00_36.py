"""v4.00.36 — contract tests for tenant_mask_wiring."""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.platform_runtime.tenant_mask_wiring import (
    RegionalMaskingMixin,
    derive_region_for_school,
    mask_dict_for_school,
    mask_payload,
)


class DeriveRegionTests(SimpleTestCase):
    def test_none_school(self):
        self.assertIsNone(derive_region_for_school(None))

    def test_data_region_eu_prefix_wins(self):
        s = mock.Mock(data_region="eu_central", country_code="US")
        self.assertEqual(derive_region_for_school(s), "EU")

    def test_country_code_eu_member(self):
        s = mock.Mock(data_region="", country_code="DE")
        self.assertEqual(derive_region_for_school(s), "EU")

    def test_country_code_us(self):
        s = mock.Mock(data_region="", country_code="US")
        self.assertEqual(derive_region_for_school(s), "US")

    def test_non_gdpr_non_ccpa_country(self):
        s = mock.Mock(data_region="", country_code="NG")
        self.assertIsNone(derive_region_for_school(s))


class MaskPayloadTests(SimpleTestCase):
    def test_passthrough_when_region_none(self):
        s = mock.Mock(data_region="", country_code="NG")
        record = {"first_name": "Alice", "email": "a@b.com"}
        out = mask_dict_for_school(record, s)
        self.assertEqual(out, record)

    def test_list_payload_recurses(self):
        s = mock.Mock(data_region="", country_code="NG")
        payload = [{"x": 1}, {"x": 2}]
        out = mask_payload(payload, s)
        self.assertEqual(out, payload)

    def test_drf_results_envelope_recurses(self):
        s = mock.Mock(data_region="", country_code="NG")
        payload = {"results": [{"x": 1}, {"x": 2}], "count": 2}
        out = mask_payload(payload, s)
        self.assertEqual(out["count"], 2)
        self.assertEqual(out["results"], [{"x": 1}, {"x": 2}])


class RegionalMaskingMixinContractTests(SimpleTestCase):
    """Confirm the mixin wraps finalize_response without breaking the chain."""

    def test_no_school_short_circuits(self):
        request = mock.Mock()
        request.school = None
        request.user = mock.Mock(school=None)
        response = mock.Mock(data={"first_name": "Alice"})

        class TestView(RegionalMaskingMixin):
            def finalize_response(self, request, response, *args, **kwargs):
                return response

        result = TestView().finalize_response(request, response)
        # No school → mask is no-op; first_name preserved.
        self.assertEqual(result.data["first_name"], "Alice")

    def test_super_finalize_response_called(self):
        request = mock.Mock()
        request.school = None
        request.user = mock.Mock(school=None)
        response = mock.Mock(data={"x": 1})
        super_called: list[bool] = []

        class Parent:
            def finalize_response(self, request, response, *args, **kwargs):
                super_called.append(True)
                return response

        class TestView(RegionalMaskingMixin, Parent):
            pass

        result = TestView().finalize_response(request, response)
        self.assertTrue(super_called)
        self.assertEqual(result.data["x"], 1)
