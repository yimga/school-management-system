"""v4.00.36 — unit tests for apps.billing.storage_metering."""

from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.billing import storage_metering as mod


class RecordStorageChangeTests(SimpleTestCase):
    def test_none_school_is_noop(self):
        with mock.patch("apps.billing.models_metering.record") as record_mock:
            mod.record_storage_change(None, 1024)
        record_mock.assert_not_called()

    def test_zero_delta_is_noop(self):
        school = mock.Mock(pk=7)
        with mock.patch("apps.billing.models_metering.record") as record_mock:
            mod.record_storage_change(school, 0)
        record_mock.assert_not_called()

    def test_positive_delta_calls_record(self):
        school = mock.Mock(pk=7)
        with mock.patch("apps.billing.models_metering.record") as record_mock:
            mod.record_storage_change(school, 2048)
        record_mock.assert_called_once_with(school, "storage_bytes", delta=2048)

    def test_non_int_delta_silently_skipped(self):
        school = mock.Mock(pk=7)
        with mock.patch("apps.billing.models_metering.record") as record_mock:
            mod.record_storage_change(school, "not-a-number")
        record_mock.assert_not_called()

    def test_negative_delta_routes_through_clamped(self):
        school = mock.Mock(pk=7)
        with mock.patch(
            "apps.billing.storage_metering._decrement_clamped"
        ) as dec_mock:
            mod.record_storage_change(school, -512)
        dec_mock.assert_called_once_with(school, 512)


class SafeSizeTests(SimpleTestCase):
    def test_none_field_returns_zero(self):
        self.assertEqual(mod._safe_size(None), 0)

    def test_empty_name_returns_zero(self):
        f = mock.Mock(name="", size=999)
        f.name = ""
        self.assertEqual(mod._safe_size(f), 0)

    def test_size_returned(self):
        f = mock.Mock()
        f.name = "uploads/x.pdf"
        f.size = 4096
        self.assertEqual(mod._safe_size(f), 4096)

    def test_size_oserror_swallowed(self):
        f = mock.Mock()
        f.name = "uploads/x.pdf"
        type(f).size = mock.PropertyMock(side_effect=OSError("file missing"))
        self.assertEqual(mod._safe_size(f), 0)
