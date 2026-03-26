from unittest import mock

from django.test import SimpleTestCase

from apps.portal.document_service import convert_document, infer_document_family


class DocumentServiceTests(SimpleTestCase):
    def test_infer_document_family(self):
        self.assertEqual(infer_document_family("a.ods"), "calc")
        self.assertEqual(infer_document_family("a.pptx"), "impress")
        self.assertEqual(infer_document_family("a.odt"), "writer")

    @mock.patch("apps.portal.document_service.convert_to_pdf", return_value=b"pdf")
    def test_writer_dispatch(self, convert_to_pdf_mock):
        self.assertEqual(convert_document("x.odt", target="pdf"), b"pdf")
        convert_to_pdf_mock.assert_called_once()

    @mock.patch("apps.portal.document_service.convert_calc_to_xlsx", return_value=b"xlsx")
    def test_calc_dispatch(self, convert_calc_to_xlsx_mock):
        self.assertEqual(convert_document("x.ods", target="xlsx"), b"xlsx")
        convert_calc_to_xlsx_mock.assert_called_once()

    @mock.patch("apps.portal.document_service.convert_impress_to_pptx", return_value=b"pptx")
    def test_impress_dispatch(self, convert_impress_to_pptx_mock):
        self.assertEqual(convert_document("x.odp", target="pptx"), b"pptx")
        convert_impress_to_pptx_mock.assert_called_once()
