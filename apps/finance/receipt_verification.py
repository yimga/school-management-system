"""
Receipt Verification Service

Extracts data from payment receipts (cash/bank) and verifies them against invoices.
All OCR goes through DocumentExtractionProvider (siteconfig.document_extraction); no direct pytesseract/cloud in app code.
"""

import logging
import re
import subprocess
import tempfile
from decimal import Decimal, InvalidOperation
from typing import Optional, Dict, Any
from django.core.files.uploadedfile import UploadedFile
from PIL import Image

from .ocr_runtime import get_ocr_runtime_status
from apps.siteconfig.document_extraction import get_document_extraction_provider


class ReceiptVerificationService:
    """Service for extracting and verifying payment receipt data."""

    def __init__(
        self,
        verification_method: str = "pattern",
        marksheet_ocr_command: str | None = None,
    ):
        """
        Initialize verification service.

        Args:
            verification_method: "pattern" (free), "ocr_tesseract" (free, requires pytesseract),
                                "ocr_cloud_google" (paid), "ocr_cloud_aws" (paid)
        """
        self.verification_method = verification_method
        self.marksheet_ocr_command = marksheet_ocr_command or ""
        self.runtime_status = get_ocr_runtime_status(
            verification_method,
            self.marksheet_ocr_command,
        )

    def extract_receipt_data(self, receipt_file: UploadedFile) -> Dict[str, Any]:
        """
        Extract amount, reference, and date from receipt file.

        Returns:
            {
                "amount": Decimal | None,
                "reference": str | None,
                "date": date | None,
                "confidence": float,  # 0.0-1.0
                "extraction_method": str,
                "raw_text": str  # Extracted text (for debugging)
            }
        """
        # Guard against unavailable OCR runtimes for non-pattern modes.
        if self.verification_method != "pattern" and not self.runtime_status.get(
            "ready", False
        ):
            missing = "; ".join(self.runtime_status.get("missing") or [])
            return {
                "amount": None,
                "reference": None,
                "date": None,
                "confidence": 0.0,
                "extraction_method": f"{self.verification_method}_not_ready",
                "raw_text": (
                    f"{self.runtime_status.get('message', 'OCR runtime not ready.')}"
                    + (f" Missing: {missing}" if missing else "")
                ),
            }

        # Read file content
        if receipt_file.name.endswith(".pdf"):
            # PDF handling would require pdfplumber or PyPDF2
            # For now, return empty - can be enhanced later
            return {
                "amount": None,
                "reference": None,
                "date": None,
                "confidence": 0.0,
                "extraction_method": "pdf_not_supported_yet",
                "raw_text": "",
            }

        # For images, try to extract text
        try:
            image = Image.open(receipt_file)
            # Convert to text via DocumentExtractionProvider (required; no direct OCR in app code)
            if self.verification_method == "pattern":
                text = self._extract_text_from_image_simple(image)
            else:
                provider = get_document_extraction_provider(
                    self.verification_method,
                    tesseract_cmd=self.marksheet_ocr_command or None,
                )
                text = provider.extract_text(image) if provider.is_available() else ""

            # Extract data from text
            amount = self._extract_amount(text)
            reference = self._extract_reference(text)
            date = self._extract_date(text)

            # Calculate confidence based on what we found
            confidence = 0.0
            if amount:
                confidence += 0.5
            if reference:
                confidence += 0.3
            if date:
                confidence += 0.2

            return {
                "amount": amount,
                "reference": reference,
                "date": date,
                "confidence": min(confidence, 1.0),
                "extraction_method": self.verification_method,
                "raw_text": text[:500],  # Limit text length
            }
        except (ValueError, TypeError, OSError, UnicodeDecodeError) as e:
            return {
                "amount": None,
                "reference": None,
                "date": None,
                "confidence": 0.0,
                "extraction_method": "error",
                "raw_text": f"Error: {str(e)}",
            }

    def _extract_text_from_image_simple(self, image: Image.Image) -> str:
        """
        Best-effort extraction without paid providers.
        Tries a lightweight preprocessing pass then reuses Tesseract paths.
        """
        processed = image.convert("L")
        # Simple threshold improves many paper scans with dark text on bright background.
        processed = processed.point(lambda x: 0 if x < 165 else 255, mode="1")
        text = self._extract_text_with_tesseract(processed)
        if text:
            return text
        # Fall back to original image if thresholding removes useful detail.
        return self._extract_text_with_tesseract(image)

    def _extract_text_with_tesseract(self, image: Image.Image) -> str:
        """Extract text via DocumentExtractionProvider (no direct pytesseract in app code)."""
        provider = get_document_extraction_provider(
            "ocr_tesseract",
            tesseract_cmd=self.marksheet_ocr_command or None,
        )
        text = provider.extract_text(image) if provider.is_available() else ""
        if text and text.strip():
            return text
        return self._extract_text_with_tesseract_cli(image)

    def _extract_text_with_tesseract_cli(self, image: Image.Image) -> str:
        """
        CLI fallback when pytesseract is unavailable.
        Uses system `tesseract` command if installed.
        """
        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                src_path = f"{tmp_dir}/scan.png"
                out_base = f"{tmp_dir}/ocr"
                out_path = f"{out_base}.txt"
                image.save(src_path, format="PNG")
                cmd = ["tesseract", src_path, out_base]
                completed = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=25,
                )
                if completed.returncode != 0:
                    logging.getLogger(__name__).warning(
                        "Receipt OCR tesseract failed: returncode=%s stderr=%s",
                        completed.returncode,
                        (completed.stderr or "")[:200],
                    )
                    return ""
                with open(out_path, "r", encoding="utf-8", errors="ignore") as handle:
                    text = handle.read()
                return text.strip()
        except subprocess.TimeoutExpired:
            logging.getLogger(__name__).warning("Receipt OCR tesseract timed out (25s)")
            return ""
        except (OSError, IOError, ValueError, TypeError, UnicodeDecodeError) as e:
            logging.getLogger(__name__).debug("Receipt OCR tesseract error: %s", e)
            return ""

    def _extract_amount(self, text: str) -> Optional[Decimal]:
        """
        Extract amount from text using pattern matching.

        Looks for patterns like:
        - "50,000 XAF"
        - "Amount: 50000"
        - "Total: 50,000.00"
        """
        if not text:
            return None

        # Common patterns for amounts
        patterns = [
            # Currency + amount patterns
            r"(\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})?)\s*(?:XAF|FCFA|CFA|USD|EUR)",
            r"(?:XAF|FCFA|CFA|USD|EUR)\s*(\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})?)",
            # Label + amount patterns
            r"(?:Amount|Total|Paid|Payment)[:\s]+(\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})?)",
            r"(\d{1,3}(?:[,\s]\d{3})*(?:\.\d{2})?)\s*(?:XAF|FCFA|CFA)",
            # Simple number patterns (large numbers likely to be amounts)
            r"\b(\d{4,}(?:[,\s]\d{3})*(?:\.\d{2})?)\b",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # Take the largest number (likely the total amount)
                amounts = []
                for match in matches:
                    # Clean the match (remove spaces, commas)
                    cleaned = match.replace(",", "").replace(" ", "")
                    try:
                        amount = Decimal(cleaned)
                        amounts.append(amount)
                    except (InvalidOperation, ValueError):
                        continue

                if amounts:
                    # Return the largest amount (likely the total)
                    return max(amounts)

        return None

    def _extract_reference(self, text: str) -> Optional[str]:
        """
        Extract transaction reference from text.

        Looks for patterns like:
        - "Reference: TXN123456"
        - "Transaction ID: 123456789"
        - "Ref: ABC123"
        """
        if not text:
            return None

        patterns = [
            r"(?:Reference|Ref|Transaction\s+ID|TXN|Txn)[:\s]+([A-Z0-9]{6,20})",
            r"\b([A-Z]{2,}\d{4,})\b",  # Pattern like "TXN123456"
            r"\b(\d{8,})\b",  # Long numeric references
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                # Return the first match
                return matches[0].strip()

        return None

    def _extract_date(self, text: str) -> Optional[str]:
        """
        Extract date from text.

        Looks for date patterns like:
        - "2026-02-03"
        - "03/02/2026"
        - "Feb 3, 2026"
        """
        if not text:
            return None

        patterns = [
            r"\b(\d{4}-\d{2}-\d{2})\b",  # YYYY-MM-DD
            r"\b(\d{2}/\d{2}/\d{4})\b",  # DD/MM/YYYY or MM/DD/YYYY
            r"\b(\d{2}-\d{2}-\d{4})\b",  # DD-MM-YYYY
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            if matches:
                return matches[0]

        return None

    def verify_receipt_match(
        self,
        receipt_data: Dict[str, Any],
        invoice,
        amount_tolerance: Decimal = Decimal("1.00"),
    ) -> Dict[str, Any]:
        """
        Verify receipt matches invoice.

        Args:
            receipt_data: Extracted receipt data from extract_receipt_data()
            invoice: Invoice instance
            amount_tolerance: Allowed difference in amount (default 1.00)

        Returns:
            {
                "matches": bool,
                "amount_match": bool,
                "reference_match": bool,
                "confidence": float,
                "discrepancies": list[str]
            }
        """
        discrepancies = []
        amount_match = False
        reference_match = False

        # Check amount match
        if receipt_data.get("amount"):
            receipt_amount = receipt_data["amount"]
            invoice_balance = invoice.balance_amount

            amount_diff = abs(receipt_amount - invoice_balance)
            amount_match = amount_diff <= amount_tolerance

            if not amount_match:
                discrepancies.append(
                    f"Amount mismatch: Receipt shows {receipt_amount}, "
                    f"Invoice balance is {invoice_balance} (difference: {amount_diff})"
                )
        else:
            discrepancies.append("Could not extract amount from receipt")

        # Check reference match
        if receipt_data.get("reference"):
            receipt_ref = receipt_data["reference"].upper()
            invoice_ref = (invoice.payment_code or invoice.reference or "").upper()

            if invoice_ref:
                reference_match = (
                    receipt_ref == invoice_ref
                    or receipt_ref in invoice_ref
                    or invoice_ref in receipt_ref
                )
                if not reference_match:
                    discrepancies.append(
                        f"Reference mismatch: Receipt shows '{receipt_data['reference']}', "
                        f"Invoice reference is '{invoice.payment_code or invoice.reference}'"
                    )
        else:
            # Reference not found, but not necessarily a problem
            pass

        # Calculate overall confidence
        confidence = receipt_data.get("confidence", 0.0)
        if amount_match:
            confidence = min(confidence + 0.2, 1.0)
        if reference_match:
            confidence = min(confidence + 0.1, 1.0)

        # Overall match if amount matches and confidence is reasonable
        matches = amount_match and confidence >= 0.5

        return {
            "matches": matches,
            "amount_match": amount_match,
            "reference_match": reference_match,
            "confidence": min(confidence, 1.0),
            "discrepancies": discrepancies,
        }
