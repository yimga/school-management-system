from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

try:
    from PIL import Image
    import pytesseract
    from pytesseract import Output, TesseractNotFoundError
except ImportError:  # pragma: no cover
    Image = None  # type: ignore[assignment]
    pytesseract = None  # type: ignore[assignment]
    Output = None  # type: ignore[assignment]
    TesseractNotFoundError = Exception  # fallback

logger = logging.getLogger(__name__)

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
    except Exception as exc:  # pragma: no cover
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
    """Run OCR on an uploaded marksheet and slice it into student rows."""
    _configure_tesseract(tesseract_cmd)
    if pytesseract is None or Image is None:
        return {
            "success": False,
            "message": "OCR backend (pytesseract + Pillow) is not configured.",
            "entries": [],
            "confidence": 0.0,
            "preview_text": "",
        }

    try:
        file_obj.seek(0)
        image = Image.open(file_obj)
        # Apply preprocessing for better handwriting recognition
        image = _preprocess_image(image)
    except Exception as exc:  # pragma: no cover
        logger.exception("Failed to decode marksheet file for OCR", exc_info=exc)
        return {
            "success": False,
            "message": "Unable to read the uploaded file (supported: PNG/JPG).",
            "entries": [],
            "confidence": 0.0,
            "preview_text": "",
        }

    try:
        preview_text = pytesseract.image_to_string(image, lang="eng")
    except Exception as exc:
        logger.exception("OCR engine error", exc_info=exc)
        return {
            "success": False,
            "message": "OCR engine failed. Check server logs for details.",
            "entries": [],
            "confidence": 0.0,
            "preview_text": "",
        }

    entries, field_confidences = _parse_text_with_confidence(image)
    overall_confidence = _estimate_confidence(image)

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
            except Exception:
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
    except Exception:
        return _parse_text(pytesseract.image_to_string(image, lang="eng") if pytesseract else ""), {}
    
    rows = []
    field_confidences: Dict[str, List[float]] = {field: [] for field in FIELD_ORDER}
    
    # Map OCR words to lines and extract confidence
    word_idx = 0
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
            except Exception:
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
    except Exception:
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
