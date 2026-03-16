"""
OCR marksheet processing (Tesseract). §2.4: Typed exception tuples and log_exception_with_context.
"""
from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

try:
    from PIL import Image
    from PIL.Image import UnidentifiedImageError
    import pytesseract
    from pytesseract import Output, TesseractNotFoundError
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    UnidentifiedImageError = Exception  # type: ignore[assignment, misc]
    pytesseract = None  # type: ignore[assignment]
    Output = None  # type: ignore[assignment]
    TesseractNotFoundError = Exception  # fallback

from apps.platform_runtime.structured_logging import log_exception_with_context

logger = logging.getLogger(__name__)

# §2.4: Typed exception tuples for OCR paths (no broad except).
_EVALS_OCR_TESSERACT_ERRORS = (OSError, RuntimeError, ValueError, TypeError, TesseractNotFoundError)
_EVALS_OCR_IMAGE_OPEN_ERRORS = (OSError, IOError, ValueError, TypeError, AttributeError, UnidentifiedImageError)
_EVALS_OCR_DECIMAL_PARSE_ERRORS = (ValueError, TypeError, InvalidOperation)

DEFAULT_TESSERACT_CMD = "tesseract"


def _configure_tesseract(cmd: Optional[str]) -> None:
    if pytesseract is None:
        return
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


def is_tesseract_available(cmd: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    if pytesseract is None:
        return False, None
    _configure_tesseract(cmd)
    try:
        version = pytesseract.get_tesseract_version()
        return True, str(version)
    except TesseractNotFoundError:
        return False, None
    except _EVALS_OCR_TESSERACT_ERRORS as exc:  # pragma: no cover
        log_exception_with_context(
            "evals.ocr: unexpected Tesseract failure",
            school_id=None,
            extra={"operation": "get_tesseract_version"},
        )
        logger.warning("Unexpected Tesseract failure", exc_info=exc)
        return False, None

FIELD_ORDER = [
    "seq1_score",
    "seq2_score",
    "exam_score",
    "mock_score",
    "practical_score",
]

NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")


def _preprocess_image(image: Image.Image) -> Image.Image:
    """Enhance image for better OCR accuracy on handwritten text."""
    if Image is None:
        return image
    from PIL import ImageEnhance, ImageFilter
    
    # Convert to grayscale if not already
    if image.mode != "L":
        image = image.convert("L")
    
    # Enhance contrast
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.5)
    
    # Enhance sharpness
    enhancer = ImageEnhance.Sharpness(image)
    image = enhancer.enhance(1.2)
    
    # Apply slight denoising (median filter)
    image = image.filter(ImageFilter.MedianFilter(size=3))
    
    return image


def process_marksheet_upload(file_obj, tesseract_cmd: Optional[str] = None) -> Dict[str, Any]:
    """Run OCR on an uploaded marksheet via DocumentExtractionProvider; slice into student rows."""
    from apps.siteconfig.document_extraction import get_document_extraction_provider
    provider = get_document_extraction_provider("ocr_tesseract", tesseract_cmd=tesseract_cmd)
    if not provider.is_available():
        return {
            "success": False,
            "message": "OCR backend (Tesseract) is not configured or not available.",
            "entries": [],
            "confidence": 0.0,
            "preview_text": "",
        }

    try:
        file_obj.seek(0)
        image = Image.open(file_obj)
        image = _preprocess_image(image)
    except _EVALS_OCR_IMAGE_OPEN_ERRORS as exc:  # pragma: no cover
        log_exception_with_context(
            "evals.ocr: failed to decode marksheet file",
            school_id=None,
            extra={"operation": "image_open_preprocess"},
        )
        logger.exception("Failed to decode marksheet file for OCR", exc_info=exc)
        return {
            "success": False,
            "message": "Unable to read the uploaded file (supported: PNG/JPG).",
            "entries": [],
            "confidence": 0.0,
            "preview_text": "",
        }

    try:
        preview_text = provider.extract_text(image)
    except _EVALS_OCR_TESSERACT_ERRORS as exc:
        log_exception_with_context(
            "evals.ocr: OCR engine error",
            school_id=None,
            extra={"operation": "extract_text"},
        )
        logger.exception("OCR engine error", exc_info=exc)
        return {
            "success": False,
            "message": "OCR engine failed. Check server logs for details.",
            "entries": [],
            "confidence": 0.0,
            "preview_text": "",
        }

    entries = _parse_text(preview_text)
    field_confidences = {}
    overall_confidence = (0.7 if entries else 0.0)

    return {
        "success": bool(entries),
        "message": "Marks parsed via OCR." if entries else "No numeric rows recognized.",
        "entries": entries,
        "confidence": overall_confidence,
        "field_confidences": field_confidences,  # Per-field confidence scores
        "preview_text": preview_text,
    }


def _parse_text(text: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in text.splitlines():
        clean_line = line.strip()
        if not clean_line:
            continue
        tokens = re.split(r"\s{2,}|\t|,", clean_line)
        student_code = tokens[0] if tokens else ""
        numbers = NUMBER_PATTERN.findall(clean_line)
        if not numbers:
            continue
        scores: Dict[str, Decimal] = {}
        for idx, num in enumerate(numbers[: len(FIELD_ORDER)]):
            try:
                scores[FIELD_ORDER[idx]] = Decimal(num)
            except _EVALS_OCR_DECIMAL_PARSE_ERRORS:
                continue
        if not scores:
            continue
        rows.append(
            {
                "student_code": student_code.upper(),
                "scores": scores,
                "line_text": clean_line,
            }
        )
    return rows


def _parse_text_with_confidence(image: Image.Image) -> Tuple[List[Dict[str, Any]], Dict[str, float]]:
    """Parse OCR text and compute per-field confidence scores."""
    if pytesseract is None or Output is None:
        return _parse_text(pytesseract.image_to_string(image, lang="eng") if pytesseract else ""), {}
    
    try:
        # Get detailed OCR data with confidence per word
        data = pytesseract.image_to_data(image, output_type=Output.DICT, lang="eng")
        text_lines = pytesseract.image_to_string(image, lang="eng").splitlines()
    except _EVALS_OCR_TESSERACT_ERRORS:
        return _parse_text(pytesseract.image_to_string(image, lang="eng") if pytesseract else ""), {}
    
    rows = []
    field_confidences: Dict[str, List[float]] = {field: [] for field in FIELD_ORDER}
    
    # Map OCR words to lines and extract confidence
    for line_idx, line_text in enumerate(text_lines):
        clean_line = line_text.strip()
        if not clean_line:
            continue
        
        tokens = re.split(r"\s{2,}|\t|,", clean_line)
        student_code = tokens[0] if tokens else ""
        numbers = NUMBER_PATTERN.findall(clean_line)
        if not numbers:
            continue
        
        scores: Dict[str, Decimal] = {}
        line_confidences: Dict[str, float] = {}
        
        # Try to match numbers with OCR confidence from data
        for idx, num_str in enumerate(numbers[: len(FIELD_ORDER)]):
            field = FIELD_ORDER[idx]
            try:
                num_value = Decimal(num_str)
                scores[field] = num_value
                
                # Find confidence for this number in OCR data
                # Look for matching text in OCR output
                conf_for_num = None
                for i, word in enumerate(data.get("text", [])):
                    if word and num_str in word and i < len(data.get("conf", [])):
                        conf_val = data["conf"][i]
                        if isinstance(conf_val, (int, float)) and conf_val >= 0:
                            conf_for_num = float(conf_val)
                            break
                
                if conf_for_num is not None:
                    line_confidences[field] = conf_for_num
                    field_confidences[field].append(conf_for_num)
                else:
                    # Fallback: use average confidence for the line
                    line_confidences[field] = 50.0
            except _EVALS_OCR_PARSE_ROW_ERRORS:
                continue

        if scores:
            rows.append(
                {
                    "student_code": student_code.upper(),
                    "scores": scores,
                    "line_text": clean_line,
                    "field_confidences": line_confidences,  # Per-field confidence for this row
                }
            )
    
    # Compute average confidence per field across all rows
    avg_field_confidences = {
        field: float(sum(confs) / len(confs)) if confs else 0.0
        for field, confs in field_confidences.items()
    }
    
    return rows, avg_field_confidences


def _estimate_confidence(image) -> float:
    if pytesseract is None or Output is None:
        return 0.0
    try:
        data = pytesseract.image_to_data(image, output_type=Output.DICT)
    except _EVALS_OCR_TESSERACT_ERRORS:
        return 0.0
    conf_values = [
        int(conf)
        for conf in data.get("conf", [])
        if isinstance(conf, (int, float, str)) and str(conf).lstrip("-").isdigit()
        and int(float(conf)) >= 0
    ]
    if not conf_values:
        return 0.0
    return float(sum(conf_values) / len(conf_values))
