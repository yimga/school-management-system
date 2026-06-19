"""Unit tests for wizard_validators — pure functions, no DB."""

from django.test import SimpleTestCase

from apps.setup_studio import wizard_validators as v


class RequiredTests(SimpleTestCase):
    def test_none_rejects(self):
        self.assertEqual(v.validate_required(None), (False, "wizards.errors.required"))

    def test_empty_string_rejects(self):
        self.assertEqual(v.validate_required(""), (False, "wizards.errors.required"))
        self.assertEqual(v.validate_required("   "), (False, "wizards.errors.required"))

    def test_empty_list_rejects(self):
        self.assertEqual(v.validate_required([]), (False, "wizards.errors.required"))

    def test_non_empty_accepts(self):
        self.assertEqual(v.validate_required("x"), (True, None))
        self.assertEqual(v.validate_required([1]), (True, None))
        self.assertEqual(v.validate_required(0), (True, None))  # explicit zero is provided


class LengthTests(SimpleTestCase):
    def test_max_length_ok(self):
        self.assertEqual(v.validate_max_length("abc", 5), (True, None))

    def test_max_length_over(self):
        self.assertEqual(v.validate_max_length("abcdef", 3), (False, "wizards.errors.max_length"))

    def test_min_length_ok(self):
        self.assertEqual(v.validate_min_length("abc", 2), (True, None))

    def test_min_length_under(self):
        self.assertEqual(v.validate_min_length("a", 3), (False, "wizards.errors.min_length"))


class TextCapTests(SimpleTestCase):
    def test_within_cap_accepts(self):
        self.assertEqual(v.validate_text_within_cap("x" * 100, 200), (True, None))

    def test_over_cap_rejects(self):
        self.assertEqual(
            v.validate_text_within_cap("x" * 201, 200),
            (False, "wizards.errors.text_too_long"),
        )

    def test_non_string_passes_through(self):
        # Typed validators own non-str values; the cap only bounds free text.
        self.assertEqual(v.validate_text_within_cap(12345, 2), (True, None))
        self.assertEqual(v.validate_text_within_cap(None, 2), (True, None))
        self.assertEqual(v.validate_text_within_cap(["a", "b", "c"], 1), (True, None))

    def test_default_cap_is_positive(self):
        self.assertGreater(v.DEFAULT_MAX_TEXT_FIELD_LENGTH, 0)


class PatternTests(SimpleTestCase):
    def test_match(self):
        self.assertEqual(v.validate_pattern("abc123", r"^[a-z0-9]+$"), (True, None))

    def test_mismatch(self):
        self.assertEqual(
            v.validate_pattern("ABC", r"^[a-z]+$"),
            (False, "wizards.errors.pattern_mismatch"),
        )

    def test_invalid_pattern(self):
        self.assertEqual(
            v.validate_pattern("abc", "(unclosed"),
            (False, "wizards.errors.pattern_invalid"),
        )


class ChoicesTests(SimpleTestCase):
    def test_in_set(self):
        self.assertEqual(v.validate_in_choices("a", ["a", "b"]), (True, None))

    def test_not_in_set(self):
        self.assertEqual(
            v.validate_in_choices("c", ["a", "b"]),
            (False, "wizards.errors.choice_not_in_set"),
        )

    def test_list_value_all_in_set(self):
        self.assertEqual(v.validate_in_choices(["a", "b"], ["a", "b", "c"]), (True, None))

    def test_list_value_one_outside(self):
        self.assertEqual(
            v.validate_in_choices(["a", "z"], ["a", "b"]),
            (False, "wizards.errors.choice_not_in_set"),
        )


class DecimalRangeTests(SimpleTestCase):
    def test_within(self):
        self.assertEqual(v.validate_decimal_range("5.00", min="0", max="10"), (True, None))

    def test_below(self):
        self.assertEqual(
            v.validate_decimal_range("-1", min="0", max="10"),
            (False, "wizards.errors.decimal_below_min"),
        )

    def test_above(self):
        self.assertEqual(
            v.validate_decimal_range("20", min="0", max="10"),
            (False, "wizards.errors.decimal_above_max"),
        )

    def test_invalid(self):
        self.assertEqual(
            v.validate_decimal_range("not-a-number"),
            (False, "wizards.errors.decimal_invalid"),
        )


class DomainTests(SimpleTestCase):
    def test_valid(self):
        self.assertEqual(v.validate_domain_format("portal.example.org"), (True, None))
        self.assertEqual(v.validate_domain_format("a.b.c.example.com"), (True, None))

    def test_invalid(self):
        self.assertEqual(
            v.validate_domain_format("not_a_domain"),
            (False, "wizards.errors.domain_invalid"),
        )
        self.assertEqual(
            v.validate_domain_format(""),
            (False, "wizards.errors.domain_invalid"),
        )


class ColorHexTests(SimpleTestCase):
    def test_valid(self):
        self.assertEqual(v.validate_color_hex("#4F46E5"), (True, None))
        self.assertEqual(v.validate_color_hex("#abcdef"), (True, None))

    def test_invalid(self):
        self.assertEqual(v.validate_color_hex("4F46E5"), (False, "wizards.errors.color_hex_invalid"))
        self.assertEqual(v.validate_color_hex("#XYZ"), (False, "wizards.errors.color_hex_invalid"))


class FileExtensionTests(SimpleTestCase):
    def test_valid(self):
        self.assertEqual(v.validate_file_extension("logo.png", ["png", "svg"]), (True, None))
        self.assertEqual(v.validate_file_extension("logo.SVG", ["png", "svg"]), (True, None))

    def test_invalid(self):
        self.assertEqual(
            v.validate_file_extension("logo.exe", ["png", "svg"]),
            (False, "wizards.errors.file_extension_not_allowed"),
        )

    def test_no_extension(self):
        self.assertEqual(
            v.validate_file_extension("logo", ["png"]),
            (False, "wizards.errors.file_extension_invalid"),
        )

    def test_file_like_object_extension(self):
        """File-like objects (Django UploadedFile etc.) carry filename on .name."""
        class _FakeUpload:
            def __init__(self, name):
                self.name = name

        self.assertEqual(
            v.validate_file_extension(_FakeUpload("logo.png"), ["png"]),
            (True, None),
        )
        self.assertEqual(
            v.validate_file_extension(_FakeUpload("logo.exe"), ["png"]),
            (False, "wizards.errors.file_extension_not_allowed"),
        )


class FileSizeTests(SimpleTestCase):
    def test_within(self):
        self.assertEqual(v.validate_file_size_bytes(100, 200), (True, None))

    def test_over(self):
        self.assertEqual(
            v.validate_file_size_bytes(300, 200),
            (False, "wizards.errors.file_too_large"),
        )

    def test_file_like_object_size(self):
        """File-like objects carry byte count on .size."""
        class _FakeUpload:
            def __init__(self, size):
                self.size = size

        self.assertEqual(v.validate_file_size_bytes(_FakeUpload(100), 200), (True, None))
        self.assertEqual(
            v.validate_file_size_bytes(_FakeUpload(300), 200),
            (False, "wizards.errors.file_too_large"),
        )


class CsvHeaderTests(SimpleTestCase):
    def test_all_present(self):
        self.assertEqual(
            v.validate_csv_header(["name", "dob", "grade"], ["name", "dob"]),
            (True, None),
        )

    def test_missing(self):
        self.assertEqual(
            v.validate_csv_header(["name"], ["name", "dob"]),
            (False, "wizards.errors.csv_header_required_missing"),
        )


class PfxShapeTests(SimpleTestCase):
    def test_valid_magic(self):
        # PKCS#12 ASN.1 SEQUENCE prefix
        data = bytes([0x30, 0x82, 0x05, 0xA1]) + b"\x00" * 100
        self.assertEqual(v.validate_pfx_certificate_shape(data), (True, None))

    def test_too_small(self):
        self.assertEqual(
            v.validate_pfx_certificate_shape(b"\x30\x00"),
            (False, "wizards.errors.pfx_too_small"),
        )

    def test_wrong_magic(self):
        self.assertEqual(
            v.validate_pfx_certificate_shape(b"\x41" * 20),
            (False, "wizards.errors.pfx_magic_invalid"),
        )


class IsoTests(SimpleTestCase):
    def test_country(self):
        self.assertEqual(v.validate_iso_country_code("IN"), (True, None))
        self.assertEqual(
            v.validate_iso_country_code("usa"),
            (False, "wizards.errors.country_code_invalid"),
        )

    def test_currency(self):
        self.assertEqual(v.validate_iso_currency_code("USD"), (True, None))
        self.assertEqual(
            v.validate_iso_currency_code("us"),
            (False, "wizards.errors.currency_code_invalid"),
        )


class EmailShapeTests(SimpleTestCase):
    def test_valid(self):
        self.assertEqual(v.validate_email_shape("a@b.co"), (True, None))

    def test_invalid(self):
        self.assertEqual(v.validate_email_shape("not-an-email"), (False, "wizards.errors.email_invalid"))
