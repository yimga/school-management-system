from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from apps.portal.document_conversion import convert_html_to_docx


class DocumentConversionTests(SimpleTestCase):
    @mock.patch(
        "apps.portal.document_conversion.convert_to_odt", return_value=b"odt-bytes"
    )
    def test_convert_html_to_docx_uses_odt_intermediate(self, convert_to_odt_mock):
        observed = {}

        def fake_convert_to_docx(source_path: str) -> bytes:
            path = Path(source_path)
            observed["suffix"] = path.suffix
            observed["exists"] = path.exists()
            observed["bytes"] = path.read_bytes()
            return b"docx-bytes"

        with mock.patch(
            "apps.portal.document_conversion.convert_to_docx",
            side_effect=fake_convert_to_docx,
        ) as convert_to_docx_mock:
            result = convert_html_to_docx("<h1>KB</h1>", title="KB")

        self.assertEqual(result, b"docx-bytes")
        self.assertEqual(convert_to_odt_mock.call_count, 1)
        self.assertEqual(convert_to_docx_mock.call_count, 1)
        self.assertEqual(observed["suffix"], ".odt")
        self.assertTrue(observed["exists"])
        self.assertEqual(observed["bytes"], b"odt-bytes")
