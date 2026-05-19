"""Encrypted legacy_* fields must never persist SQL NULL on insert."""

from django.test import SimpleTestCase

from apps.accounts.legacy_hashes.encryption import EncryptedCharField, EncryptedJSONField


class LegacyEncryptedFieldPrepValueTests(SimpleTestCase):
    def test_charfield_empty_sentinel_is_empty_string_not_null(self):
        field = EncryptedCharField(max_length=512, blank=True, default="")
        self.assertEqual(field.get_prep_value(None), "")
        self.assertEqual(field.get_prep_value(""), "")

    def test_jsonfield_empty_sentinel_is_empty_object_literal(self):
        field = EncryptedJSONField(default=dict, blank=True)
        self.assertEqual(field.get_prep_value(None), "{}")
        self.assertEqual(field.get_prep_value({}), "{}")
