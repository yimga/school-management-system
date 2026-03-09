"""
Document extraction provider abstraction (non-negotiable). All OCR/text extraction goes through this interface.
No view or service imports pytesseract or cloud OCR SDKs directly; use get_document_extraction_provider().
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DocumentExtractionProvider(ABC):
    """Abstract base for document/text extraction (receipts, marksheets, etc.)."""

    @abstractmethod
    def extract_text(self, image: Any) -> str:
        """Extract plain text from image. image: PIL Image or path. Returns "" on failure."""
        pass

    def is_available(self) -> bool:
        """Return True if the provider is configured and usable."""
        return True


class TesseractDocumentExtractionProvider(DocumentExtractionProvider):
    """Tesseract OCR (local)."""

    def __init__(self, tesseract_cmd: Optional[str] = None):
        self._cmd = tesseract_cmd
        self._configured = False

    def _configure(self) -> None:
        if self._configured:
            return
        try:
            import pytesseract  # noqa: F401
            if self._cmd:
                pytesseract.pytesseract.tesseract_cmd = self._cmd
            self._configured = True
        except Exception:
            pass

    def is_available(self) -> bool:
        try:
            import pytesseract
            self._configure()
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def extract_text(self, image: Any) -> str:
        self._configure()
        try:
            import pytesseract
            if hasattr(image, "read"):
                from PIL import Image
                image = Image.open(image)
            return pytesseract.image_to_string(image, lang="eng") or ""
        except Exception as e:
            logger.warning("Tesseract extract_text failed: %s", e)
            return ""


class PatternDocumentExtractionProvider(DocumentExtractionProvider):
    """Pattern-only mode (no OCR); returns empty string."""

    def extract_text(self, image: Any) -> str:
        return ""


class GoogleVisionDocumentExtractionProvider(DocumentExtractionProvider):
    """Google Cloud Vision API. Requires GOOGLE_CLOUD_VISION_API_KEY or GOOGLE_APPLICATION_CREDENTIALS."""

    def is_available(self) -> bool:
        import os
        return bool((os.getenv("GOOGLE_CLOUD_VISION_API_KEY") or "").strip()) or bool(
            (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
        )

    def extract_text(self, image: Any) -> str:
        if not self.is_available():
            return ""
        try:
            from google.cloud import vision
            client = vision.ImageAnnotatorClient()
            if hasattr(image, "read"):
                content = image.read()
            elif hasattr(image, "tobytes"):
                content = image.tobytes()
            else:
                content = image
            response = client.document_text_detection(image=vision.Image(content=content))
            if response.full_text_annotation:
                return response.full_text_annotation.text or ""
            return ""
        except ImportError:
            logger.warning("google-cloud-vision not installed")
            return ""
        except Exception as e:
            logger.warning("Google Vision extract_text failed: %s", e)
            return ""


class AWSTextractDocumentExtractionProvider(DocumentExtractionProvider):
    """AWS Textract. Requires AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION."""

    def is_available(self) -> bool:
        import os
        return bool((os.getenv("AWS_ACCESS_KEY_ID") or "").strip()) and bool(
            (os.getenv("AWS_SECRET_ACCESS_KEY") or "").strip()
        ) and bool((os.getenv("AWS_DEFAULT_REGION") or "").strip())

    def extract_text(self, image: Any) -> str:
        if not self.is_available():
            return ""
        try:
            import boto3
            client = boto3.client("textract")
            if hasattr(image, "read"):
                content = image.read()
            elif hasattr(image, "tobytes"):
                content = image.tobytes()
            else:
                content = image
            response = client.detect_document_text(Document={"Bytes": content})
            lines = []
            for item in response.get("Blocks", []):
                if item.get("BlockType") == "LINE":
                    lines.append(item.get("Text", ""))
            return "\n".join(lines)
        except ImportError:
            logger.warning("boto3 not installed")
            return ""
        except Exception as e:
            logger.warning("AWS Textract extract_text failed: %s", e)
            return ""


def get_document_extraction_provider(
    method: str,
    tesseract_cmd: Optional[str] = None,
) -> DocumentExtractionProvider:
    """Return the configured document extraction provider. All OCR must use this (no direct pytesseract/cloud in app code)."""
    method = (method or "pattern").strip().lower()
    if method == "pattern":
        return PatternDocumentExtractionProvider()
    if method == "ocr_tesseract":
        return TesseractDocumentExtractionProvider(tesseract_cmd=tesseract_cmd)
    if method == "ocr_cloud_google":
        return GoogleVisionDocumentExtractionProvider()
    if method == "ocr_cloud_aws":
        return AWSTextractDocumentExtractionProvider()
    return PatternDocumentExtractionProvider()
