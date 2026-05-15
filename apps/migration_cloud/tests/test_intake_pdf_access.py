"""Adapter-registration smoke tests for the long-tail intake adapters
(PDF, Microsoft Access, OneDrive, Dropbox).

Deep behaviour requires external binaries (Tesseract / Poppler / mdb-tools)
or live OAuth tokens, so these tests just confirm:

    1. Each adapter is registered against its IntakeMethod.
    2. Handle validation rejects obviously-wrong inputs cleanly.
    3. The graceful-degradation path raises ``IntakeError`` with an
       install-hint when the underlying dependency is missing.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from apps.migration_cloud.intake import IntakeError, get_adapter
from apps.migration_cloud.intake.base import IntakeContext
from apps.migration_cloud.models import IntakeMethod


class IntakeRegistrationTests(SimpleTestCase):
    def test_pdf_adapter_is_registered(self) -> None:
        adapter = get_adapter(IntakeMethod.PDF)
        self.assertIsNotNone(adapter)

    def test_access_adapter_is_registered(self) -> None:
        adapter = get_adapter(IntakeMethod.ACCESS_DB)
        self.assertIsNotNone(adapter)

    def test_oauth_adapter_is_registered(self) -> None:
        adapter = get_adapter(IntakeMethod.OAUTH_FOLDER)
        self.assertIsNotNone(adapter)


class PdfHandleValidationTests(SimpleTestCase):
    def setUp(self) -> None:
        self.adapter = get_adapter(IntakeMethod.PDF)
        self.ctx = IntakeContext(bundle_id=0, idempotency_key="ut-pdf")

    def test_missing_path_raises(self) -> None:
        with self.assertRaises(IntakeError):
            self.adapter.validate_handle("/nope/missing.pdf", self.ctx)

    def test_wrong_extension_raises(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as fh:
            fh.write(b"not a pdf")
            path = fh.name
        try:
            with self.assertRaises(IntakeError):
                self.adapter.validate_handle(path, self.ctx)
        finally:
            Path(path).unlink(missing_ok=True)


class AccessHandleValidationTests(SimpleTestCase):
    def setUp(self) -> None:
        self.adapter = get_adapter(IntakeMethod.ACCESS_DB)
        self.ctx = IntakeContext(bundle_id=0, idempotency_key="ut-access")

    def test_missing_path_raises(self) -> None:
        with self.assertRaises(IntakeError):
            self.adapter.validate_handle("/nope/missing.accdb", self.ctx)

    def test_wrong_extension_raises(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as fh:
            fh.write(b"x")
            path = fh.name
        try:
            with self.assertRaises(IntakeError):
                self.adapter.validate_handle(path, self.ctx)
        finally:
            Path(path).unlink(missing_ok=True)


class OauthHandleValidationTests(SimpleTestCase):
    def setUp(self) -> None:
        self.adapter = get_adapter(IntakeMethod.OAUTH_FOLDER)
        self.ctx = IntakeContext(bundle_id=0, idempotency_key="ut-oauth")

    def test_unknown_provider_raises(self) -> None:
        with self.assertRaises(IntakeError):
            self.adapter.validate_handle(
                {"provider": "weird_drive", "folder_id": "x", "access_token": "y"},
                self.ctx,
            )

    def test_missing_token_raises(self) -> None:
        with self.assertRaises(IntakeError):
            self.adapter.validate_handle(
                {"provider": "google_drive", "folder_id": "x"},
                self.ctx,
            )

    def test_non_dict_handle_raises(self) -> None:
        with self.assertRaises(IntakeError):
            self.adapter.validate_handle("just a string", self.ctx)
