"""
Fraud Detection Service for Payment Receipt Uploads

Detects and flags suspicious receipts to prevent fraud:
- Date manipulation (old receipts with edited dates)
- Duplicate receipts
- File metadata anomalies
- Suspicious upload patterns
"""

import hashlib
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional
from django.utils import timezone
from django.core.files.uploadedfile import UploadedFile
from PIL import Image
from PIL.ExifTags import TAGS
import os


#: Score at or above which a receipt must NOT be auto-applied and must go to a
#: human. Single source of truth: the live auto-apply decision and its dry-run
#: twin both read this. They previously each hardcoded ``70`` and drifted —
#: the dry-run kept its fraud term while the live path lost one, so a dry run
#: reported ``would_apply: False`` for a receipt the live run credited.
FRAUD_REVIEW_SCORE_THRESHOLD = 70


class ReceiptFraudDetector:
    """Detects fraudulent receipt uploads."""

    # Configuration thresholds
    MAX_RECEIPT_AGE_DAYS = 90  # Flag receipts older than 90 days
    FUTURE_DATE_TOLERANCE_DAYS = 1  # Allow 1 day in future (timezone differences)
    SUSPICIOUS_UPLOAD_WINDOW_HOURS = 24  # Multiple uploads within 24 hours
    SUSPICIOUS_UPLOAD_COUNT = 3  # Flag if 3+ uploads in window

    def __init__(self):
        pass

    def detect_fraud(
        self,
        receipt_file: UploadedFile,
        receipt_date: Optional[str],
        transaction_reference: str,
        uploaded_by_id: int,
        invoice_id: int,
        uploaded_amount: Optional[Decimal],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, any]:
        """
        Comprehensive fraud detection for receipt uploads.

        Returns:
            {
                "fraud_risk_score": int (0-100),
                "fraud_flags": list[str],
                "file_hash": str,
                "recommendation": "auto_approve" | "review" | "reject",
                "details": dict
            }
        """
        fraud_flags = []
        risk_score = 0
        details = {}

        # 1. Calculate file hash for duplicate detection
        file_hash = self._calculate_file_hash(receipt_file)
        details["file_hash"] = file_hash

        # 2. Check for duplicate file hash
        duplicate_file = self._check_duplicate_file_hash(file_hash, invoice_id)
        if duplicate_file:
            fraud_flags.append("duplicate_file")
            risk_score += 50
            details["duplicate_file"] = {
                "existing_upload_id": duplicate_file.id,
                "existing_upload_date": duplicate_file.created_at.isoformat(),
                "existing_status": duplicate_file.status,
            }

        # 3. Check for duplicate transaction reference
        if transaction_reference:
            duplicate_ref = self._check_duplicate_transaction_reference(
                transaction_reference, invoice_id
            )
            if duplicate_ref:
                fraud_flags.append("duplicate_reference")
                risk_score += 40
                details["duplicate_reference"] = {
                    "existing_upload_id": duplicate_ref.id,
                    "existing_upload_date": duplicate_ref.created_at.isoformat(),
                    "existing_status": duplicate_ref.status,
                }

        # 4. Date validation
        date_validation = self._validate_receipt_date(receipt_date)
        if not date_validation["valid"]:
            fraud_flags.append(date_validation["flag"])
            risk_score += date_validation["risk_score"]
            details["date_validation"] = date_validation

        # 5. File metadata analysis
        metadata_analysis = self._analyze_file_metadata(receipt_file)
        if metadata_analysis["suspicious"]:
            fraud_flags.extend(metadata_analysis["flags"])
            risk_score += metadata_analysis["risk_score"]
            details["metadata_analysis"] = metadata_analysis

        # 6. Upload pattern analysis
        pattern_analysis = self._analyze_upload_pattern(uploaded_by_id, invoice_id)
        if pattern_analysis["suspicious"]:
            fraud_flags.extend(pattern_analysis["flags"])
            risk_score += pattern_analysis["risk_score"]
            details["upload_pattern"] = pattern_analysis

        # 7. Amount validation (if provided)
        if uploaded_amount:
            amount_validation = self._validate_amount(uploaded_amount, invoice_id)
            if not amount_validation["valid"]:
                fraud_flags.append(amount_validation["flag"])
                risk_score += amount_validation["risk_score"]
                details["amount_validation"] = amount_validation

        # Cap risk score at 100
        risk_score = min(risk_score, 100)

        # Determine recommendation
        if risk_score >= 70:
            recommendation = "reject"
        elif risk_score >= 40:
            recommendation = "review"
        else:
            recommendation = "auto_approve"

        return {
            "fraud_risk_score": risk_score,
            "fraud_flags": list(set(fraud_flags)),  # Remove duplicates
            "file_hash": file_hash,
            "recommendation": recommendation,
            "details": details,
        }

    def _calculate_file_hash(self, receipt_file: UploadedFile) -> str:
        """Calculate SHA-256 hash of receipt file."""
        receipt_file.seek(0)  # Reset file pointer
        file_content = receipt_file.read()
        receipt_file.seek(0)  # Reset again for later use
        return hashlib.sha256(file_content).hexdigest()

    def _check_duplicate_file_hash(
        self, file_hash: str, exclude_invoice_id: Optional[int] = None
    ) -> Optional[any]:
        """Check if same file hash was uploaded before."""
        from .models import PaymentProofUpload

        query = PaymentProofUpload.objects.filter(file_hash=file_hash)
        if exclude_invoice_id:
            # Allow same file for same invoice (re-upload), but flag if used for different invoice
            query = query.exclude(invoice_id=exclude_invoice_id)

        return query.order_by("-created_at").first()

    def _check_duplicate_transaction_reference(
        self, transaction_reference: str, exclude_invoice_id: Optional[int] = None
    ) -> Optional[any]:
        """Check if same transaction reference was used before."""
        from .models import PaymentProofUpload

        query = PaymentProofUpload.objects.filter(
            transaction_reference__iexact=transaction_reference
        ).exclude(status=PaymentProofUpload.Status.REJECTED)

        if exclude_invoice_id:
            query = query.exclude(invoice_id=exclude_invoice_id)

        return query.order_by("-created_at").first()

    def _validate_receipt_date(self, receipt_date_str: Optional[str]) -> Dict:
        """Validate receipt date against current date."""
        if not receipt_date_str:
            return {
                "valid": True,
                "flag": None,
                "risk_score": 0,
                "reason": "No date extracted from receipt",
            }

        try:
            # Parse date string (handles various formats)
            receipt_date = self._parse_date(receipt_date_str)
            if not receipt_date:
                return {
                    "valid": True,
                    "flag": None,
                    "risk_score": 0,
                    "reason": "Could not parse date",
                }

            today = timezone.now().date()
            days_old = (today - receipt_date).days

            # Check if receipt is too old
            if days_old > self.MAX_RECEIPT_AGE_DAYS:
                return {
                    "valid": False,
                    "flag": "old_receipt",
                    "risk_score": 30,
                    "reason": f"Receipt is {days_old} days old (max allowed: {self.MAX_RECEIPT_AGE_DAYS} days)",
                    "receipt_date": receipt_date.isoformat(),
                    "days_old": days_old,
                }

            # Check if receipt is in future (beyond tolerance)
            if days_old < -self.FUTURE_DATE_TOLERANCE_DAYS:
                return {
                    "valid": False,
                    "flag": "future_date",
                    "risk_score": 50,
                    "reason": f"Receipt date is in the future: {receipt_date.isoformat()}",
                    "receipt_date": receipt_date.isoformat(),
                }

            # Check if receipt is suspiciously old but within limit
            if days_old > 30:
                return {
                    "valid": True,
                    "flag": None,
                    "risk_score": 10,  # Low risk, but flag for review
                    "reason": f"Receipt is {days_old} days old (may need verification)",
                    "receipt_date": receipt_date.isoformat(),
                    "days_old": days_old,
                }

            return {
                "valid": True,
                "flag": None,
                "risk_score": 0,
                "receipt_date": receipt_date.isoformat(),
                "days_old": days_old,
            }
        except (ValueError, TypeError, AttributeError) as e:
            return {
                "valid": True,
                "flag": None,
                "risk_score": 0,
                "reason": f"Date validation error: {str(e)}",
            }

    def _parse_date(self, date_str: str):
        """Parse date string in various formats."""
        from datetime import datetime

        formats = [
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%m/%d/%Y",
            "%d-%m-%Y",
            "%Y/%m/%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt).date()
            except ValueError:
                continue

        return None

    def _analyze_file_metadata(self, receipt_file: UploadedFile) -> Dict:
        """Analyze file metadata for anomalies."""
        flags = []
        risk_score = 0
        details = {}

        try:
            # Check file extension vs actual content
            file_name = receipt_file.name.lower()
            is_image = file_name.endswith((".jpg", ".jpeg", ".png", ".gif"))
            _is_pdf = file_name.endswith(".pdf")

            if is_image:
                try:
                    image = Image.open(receipt_file)
                    receipt_file.seek(0)  # Reset

                    # Check EXIF data
                    exif_data = image._getexif()
                    if exif_data:
                        exif_info = {}
                        for tag_id, value in exif_data.items():
                            tag = TAGS.get(tag_id, tag_id)
                            exif_info[tag] = value

                        details["exif_data"] = exif_info

                        # Check if image was recently created/modified
                        # (EXIF DateTimeOriginal, DateTimeDigitized, DateTime)
                        date_fields = [
                            "DateTimeOriginal",
                            "DateTimeDigitized",
                            "DateTime",
                        ]
                        for field in date_fields:
                            if field in exif_info:
                                # Could compare with upload date here
                                pass

                    # Check image dimensions (suspicious if very small or very large)
                    width, height = image.size
                    if width < 100 or height < 100:
                        flags.append("suspicious_image_size")
                        risk_score += 5
                        details["image_size"] = {"width": width, "height": height}

                except (OSError, IOError, AttributeError, TypeError, ValueError) as e:
                    details["image_analysis_error"] = str(e)

            # Check file size (suspicious if very small - might be edited/cropped)
            receipt_file.seek(0, os.SEEK_END)
            file_size = receipt_file.tell()
            receipt_file.seek(0)

            if file_size < 5000:  # Less than 5KB
                flags.append("suspicious_file_size")
                risk_score += 10
                details["file_size"] = file_size

        except (OSError, IOError, AttributeError, TypeError, ValueError) as e:
            details["metadata_analysis_error"] = str(e)

        return {
            "suspicious": len(flags) > 0,
            "flags": flags,
            "risk_score": risk_score,
            "details": details,
        }

    def _analyze_upload_pattern(self, uploaded_by_id: int, invoice_id: int) -> Dict:
        """Analyze upload patterns for suspicious behavior."""
        from .models import PaymentProofUpload
        from datetime import timedelta

        flags = []
        risk_score = 0
        details = {}

        now = timezone.now()
        window_start = now - timedelta(hours=self.SUSPICIOUS_UPLOAD_WINDOW_HOURS)

        # Count recent uploads by this user
        recent_uploads = PaymentProofUpload.objects.filter(
            uploaded_by_id=uploaded_by_id, created_at__gte=window_start
        ).count()

        if recent_uploads >= self.SUSPICIOUS_UPLOAD_COUNT:
            flags.append("high_upload_frequency")
            risk_score += 20
            details["recent_uploads"] = recent_uploads
            details["window_hours"] = self.SUSPICIOUS_UPLOAD_WINDOW_HOURS

        # Count uploads for this invoice
        invoice_uploads = (
            PaymentProofUpload.objects.filter(invoice_id=invoice_id)
            .exclude(status=PaymentProofUpload.Status.REJECTED)
            .count()
        )

        if invoice_uploads >= 3:
            flags.append("multiple_receipts_same_invoice")
            risk_score += 15
            details["invoice_upload_count"] = invoice_uploads

        return {
            "suspicious": len(flags) > 0,
            "flags": flags,
            "risk_score": risk_score,
            "details": details,
        }

    def _validate_amount(self, uploaded_amount: Decimal, invoice_id: int) -> Dict:
        """Validate amount against invoice balance."""
        from .models import Invoice

        try:
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            invoice = Invoice.objects.get(id=invoice_id)
            invoice_balance = invoice.balance_amount

            # Check if amount exceeds invoice balance significantly
            if uploaded_amount > invoice_balance * Decimal("1.1"):  # 10% over
                return {
                    "valid": False,
                    "flag": "amount_exceeds_balance",
                    "risk_score": 25,
                    "reason": f"Amount {uploaded_amount} exceeds invoice balance {invoice_balance}",
                    "uploaded_amount": str(uploaded_amount),
                    "invoice_balance": str(invoice_balance),
                }

            # Check if amount is suspiciously low
            if uploaded_amount < invoice_balance * Decimal("0.5"):  # Less than 50%
                return {
                    "valid": False,
                    "flag": "amount_too_low",
                    "risk_score": 20,
                    "reason": f"Amount {uploaded_amount} is less than 50% of invoice balance {invoice_balance}",
                    "uploaded_amount": str(uploaded_amount),
                    "invoice_balance": str(invoice_balance),
                }

            return {"valid": True, "flag": None, "risk_score": 0}
        except Invoice.DoesNotExist:
            return {
                "valid": True,
                "flag": None,
                "risk_score": 0,
                "reason": "Invoice not found",
            }
        except (ValueError, TypeError, InvalidOperation, AttributeError) as e:
            return {
                "valid": True,
                "flag": None,
                "risk_score": 0,
                "reason": f"Amount validation error: {str(e)}",
            }

    def _analyze_ip_address(self, ip_address: str, uploaded_by_id: int) -> Dict:
        """Analyze IP address for suspicious patterns."""
        from .models import PaymentProofUpload
        from datetime import timedelta

        flags = []
        risk_score = 0
        details = {}

        now = timezone.now()
        window_start = now - timedelta(hours=24)

        # Check if same IP uploaded multiple receipts recently
        recent_uploads_same_ip = (
            PaymentProofUpload.objects.filter(
                ip_address=ip_address, created_at__gte=window_start
            )
            .exclude(uploaded_by_id=uploaded_by_id)
            .count()
        )

        if recent_uploads_same_ip >= 3:
            flags.append("multiple_users_same_ip")
            risk_score += 15
            details["recent_uploads_same_ip"] = recent_uploads_same_ip

        # Check if IP is from known VPN/proxy (basic check)
        # In production, use a VPN detection service
        vpn_indicators = ["vpn", "proxy", "tor"]
        ip_lower = ip_address.lower()
        if any(indicator in ip_lower for indicator in vpn_indicators):
            flags.append("possible_vpn_proxy")
            risk_score += 10
            details["vpn_detected"] = True

        return {
            "suspicious": len(flags) > 0,
            "flags": flags,
            "risk_score": risk_score,
            "details": details,
        }
