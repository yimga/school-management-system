"""
OCR runtime readiness helpers.

These checks keep Scan Teller predictable across environments:
- Always allow pattern mode (no external dependency)
- Verify local OCR runtime for Tesseract mode
- Verify credentials presence for cloud OCR modes
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def _has_env(name: str) -> bool:
    return bool((os.getenv(name) or "").strip())


def _credentials_file_exists(path_value: str) -> bool:
    if not path_value:
        return False
    try:
        return Path(path_value).expanduser().is_file()
    except (OSError, TypeError):
        return False


def get_ocr_runtime_status(
    verification_method: str, marksheet_ocr_command: str | None = None
) -> dict:
    method = (verification_method or "pattern").strip()

    if method == "pattern":
        return {
            "method": method,
            "provider": "pattern",
            "ready": True,
            "message": "Pattern mode is always available.",
            "missing": [],
        }

    if method == "ocr_tesseract":
        has_python_binding = False
        try:
            import pytesseract  # noqa: F401

            has_python_binding = True
        except ImportError:
            has_python_binding = False

        tesseract_cli = shutil.which("tesseract")
        custom_command = (marksheet_ocr_command or "").strip()
        ready = has_python_binding or bool(tesseract_cli) or bool(custom_command)

        missing = []
        if not ready:
            missing.append("Install `pytesseract` or system `tesseract` binary.")

        return {
            "method": method,
            "provider": "tesseract",
            "ready": ready,
            "message": (
                "Tesseract runtime available."
                if ready
                else "Tesseract runtime is not available in this environment."
            ),
            "missing": missing,
            "runtime": {
                "has_pytesseract": has_python_binding,
                "tesseract_cli": tesseract_cli or "",
                "marksheet_ocr_command": custom_command,
            },
        }

    if method == "ocr_cloud_google":
        has_api_key = _has_env("GOOGLE_CLOUD_VISION_API_KEY")
        creds_file = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
        has_credentials_file = _credentials_file_exists(creds_file)
        ready = has_api_key or has_credentials_file

        missing = []
        if not has_api_key and not has_credentials_file:
            missing.extend(
                [
                    "Set GOOGLE_CLOUD_VISION_API_KEY or GOOGLE_APPLICATION_CREDENTIALS.",
                    "If using credentials file, ensure path exists on server.",
                ]
            )

        return {
            "method": method,
            "provider": "google_vision",
            "ready": ready,
            "message": (
                "Google Vision credentials detected."
                if ready
                else "Google Vision credentials are missing."
            ),
            "missing": missing,
            "runtime": {
                "has_api_key": has_api_key,
                "credentials_file": creds_file,
                "credentials_file_exists": has_credentials_file,
            },
        }

    if method == "ocr_cloud_aws":
        has_access_key = _has_env("AWS_ACCESS_KEY_ID")
        has_secret = _has_env("AWS_SECRET_ACCESS_KEY")
        has_region = _has_env("AWS_DEFAULT_REGION")
        ready = has_access_key and has_secret and has_region

        missing = []
        if not has_access_key:
            missing.append("Set AWS_ACCESS_KEY_ID.")
        if not has_secret:
            missing.append("Set AWS_SECRET_ACCESS_KEY.")
        if not has_region:
            missing.append("Set AWS_DEFAULT_REGION.")

        return {
            "method": method,
            "provider": "aws_textract",
            "ready": ready,
            "message": (
                "AWS Textract credentials detected."
                if ready
                else "AWS Textract credentials are incomplete."
            ),
            "missing": missing,
            "runtime": {
                "has_access_key": has_access_key,
                "has_secret": has_secret,
                "has_region": has_region,
            },
        }

    return {
        "method": method,
        "provider": "unknown",
        "ready": False,
        "message": f"Unsupported OCR method: {method}",
        "missing": [
            f"Use one of: pattern, ocr_tesseract, ocr_cloud_google, ocr_cloud_aws."
        ],
    }
