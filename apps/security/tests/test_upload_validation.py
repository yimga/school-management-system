"""Tests for the shared upload-validation primitive (DB-free)."""

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings

from apps.security.upload_validation import (
    DOCUMENT_MIMES,
    RECEIPT_MIMES,
    SAFE_IMAGE_MIMES,
    UploadValidationError,
    scan_for_malware,
    sniff_file_mime,
    validate_uploaded_file,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 28
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 20
GIF = b"GIF89a" + b"\x00" * 26
BMP = b"BM" + b"\x00" * 30
TIFF_LE = b"II*\x00" + b"\x00" * 28
TIFF_BE = b"MM\x00*" + b"\x00" * 28
SVG = b"<svg xmlns='http://www.w3.org/2000/svg'><script>x</script></svg>"
PDF = b"%PDF-1.7\n" + b"\x00" * 24
PDF_LEADING = b"\r\n   \n%PDF-1.4\n" + b"\x00" * 20  # header after leading bytes
ZIP = b"PK\x03\x04" + b"\x00" * 28
HTML = b"<html><body><script>alert(1)</script></body></html>"


def _u(data, name="f", content_type="application/octet-stream"):
    return SimpleUploadedFile(name, data, content_type=content_type)


def _reject_scanner(data):
    return (False, "eicar-test-signature")


def _accept_scanner(data):
    return (True, "clean")


def _raising_scanner(data):
    raise RuntimeError("boom")


class SniffFileMimeTests(SimpleTestCase):
    def test_known_types_sniff_by_magic_bytes(self):
        self.assertEqual(sniff_file_mime(PNG), "image/png")
        self.assertEqual(sniff_file_mime(JPEG), "image/jpeg")
        self.assertEqual(sniff_file_mime(WEBP), "image/webp")
        self.assertEqual(sniff_file_mime(GIF), "image/gif")
        self.assertEqual(sniff_file_mime(SVG), "image/svg+xml")
        self.assertEqual(sniff_file_mime(PDF), "application/pdf")
        self.assertEqual(sniff_file_mime(ZIP), "application/zip")

    def test_bmp_tiff_and_lenient_pdf(self):
        self.assertEqual(sniff_file_mime(BMP), "image/bmp")
        self.assertEqual(sniff_file_mime(TIFF_LE), "image/tiff")
        self.assertEqual(sniff_file_mime(TIFF_BE), "image/tiff")
        # %PDF- after leading bytes must still resolve (spec-legal, Acrobat-lenient).
        self.assertEqual(sniff_file_mime(PDF_LEADING), "application/pdf")

    def test_unknown_and_empty_return_blank(self):
        self.assertEqual(sniff_file_mime(HTML), "")
        self.assertEqual(sniff_file_mime(b""), "")


class ReceiptAllowlistTests(SimpleTestCase):
    def test_receipt_accepts_pdf_and_jpeg(self):
        self.assertEqual(
            validate_uploaded_file(
                _u(PDF, "r.pdf"), allowed_mimes=RECEIPT_MIMES, max_bytes=1_000_000
            ),
            "application/pdf",
        )
        self.assertEqual(
            validate_uploaded_file(
                _u(JPEG, "r.jpg"), allowed_mimes=RECEIPT_MIMES, max_bytes=1_000_000
            ),
            "image/jpeg",
        )

    def test_receipt_rejects_svg_and_html(self):
        for bad in (SVG, HTML):
            with self.assertRaises(UploadValidationError):
                validate_uploaded_file(
                    _u(bad, "r.dat"), allowed_mimes=RECEIPT_MIMES, max_bytes=1_000_000
                )


class ValidateUploadedFileTests(SimpleTestCase):
    def test_real_png_passes_image_allowlist(self):
        mime = validate_uploaded_file(
            _u(PNG, "p.png", "image/png"),
            allowed_mimes=SAFE_IMAGE_MIMES,
            max_bytes=1_000_000,
        )
        self.assertEqual(mime, "image/png")

    def test_svg_declared_as_image_is_rejected(self):
        with self.assertRaises(UploadValidationError):
            validate_uploaded_file(
                _u(SVG, "x.svg", "image/svg+xml"),
                allowed_mimes=SAFE_IMAGE_MIMES,
                max_bytes=1_000_000,
            )

    def test_spoofed_content_type_is_rejected(self):
        with self.assertRaises(UploadValidationError):
            validate_uploaded_file(
                _u(HTML, "evil.png", "image/png"),
                allowed_mimes=SAFE_IMAGE_MIMES,
                max_bytes=1_000_000,
            )

    def test_gif_rejected_by_safe_image_allowlist(self):
        with self.assertRaises(UploadValidationError):
            validate_uploaded_file(
                _u(GIF, "a.gif", "image/gif"),
                allowed_mimes=SAFE_IMAGE_MIMES,
                max_bytes=1_000_000,
            )

    def test_empty_file_is_rejected(self):
        with self.assertRaises(UploadValidationError):
            validate_uploaded_file(
                _u(b"", "e.png", "image/png"),
                allowed_mimes=SAFE_IMAGE_MIMES,
                max_bytes=1_000_000,
            )

    def test_oversize_is_rejected(self):
        with self.assertRaises(UploadValidationError):
            validate_uploaded_file(
                _u(PNG, "p.png", "image/png"),
                allowed_mimes=SAFE_IMAGE_MIMES,
                max_bytes=4,
            )

    def test_pdf_passes_document_allowlist(self):
        mime = validate_uploaded_file(
            _u(PDF, "d.pdf", "application/pdf"),
            allowed_mimes=DOCUMENT_MIMES,
            max_bytes=1_000_000,
        )
        self.assertEqual(mime, "application/pdf")

    def test_read_cursor_is_restored(self):
        f = _u(PNG, "p.png", "image/png")
        validate_uploaded_file(
            f, allowed_mimes=SAFE_IMAGE_MIMES, max_bytes=1_000_000
        )
        # Caller must still be able to save the file from the start.
        self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")


class MalwareScanHookTests(SimpleTestCase):
    def test_unconfigured_reports_not_scanned_not_clean(self):
        ok, detail = scan_for_malware(b"anything")
        self.assertTrue(ok)
        self.assertEqual(detail, "av-not-configured")

    @override_settings(UPLOAD_MALWARE_SCANNER=_reject_scanner)
    def test_configured_scanner_rejects_flagged_bytes(self):
        with self.assertRaises(UploadValidationError):
            validate_uploaded_file(
                _u(PNG, "p.png", "image/png"),
                allowed_mimes=SAFE_IMAGE_MIMES,
                max_bytes=1_000_000,
            )

    @override_settings(UPLOAD_MALWARE_SCANNER=_accept_scanner)
    def test_configured_scanner_passes_clean_bytes(self):
        mime = validate_uploaded_file(
            _u(PNG, "p.png", "image/png"),
            allowed_mimes=SAFE_IMAGE_MIMES,
            max_bytes=1_000_000,
        )
        self.assertEqual(mime, "image/png")

    @override_settings(UPLOAD_MALWARE_SCANNER=_raising_scanner)
    def test_broken_scanner_fails_closed(self):
        with self.assertRaises(UploadValidationError):
            validate_uploaded_file(
                _u(PNG, "p.png", "image/png"),
                allowed_mimes=SAFE_IMAGE_MIMES,
                max_bytes=1_000_000,
            )
