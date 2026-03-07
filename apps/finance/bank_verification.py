"""
Bank Deposit Verification Service

Verifies that payments actually arrived in bank accounts by matching receipt uploads
with bank statement entries. Supports Cameroon banks, MTN MoMo, and Orange Money.
"""

from decimal import Decimal
from datetime import timedelta
from typing import Optional, Dict, List, Tuple
from django.utils import timezone
from django.db.models import Q


class BankDepositVerifier:
    """Verifies bank deposits against bank statements."""
    
    # Cameroon bank account number formats
    CAMEROON_BANK_ACCOUNT_PATTERNS = [
        r'\d{10,15}',  # Standard account numbers (10-15 digits)
    ]
    
    # MTN MoMo merchant account format
    MTN_MOMO_MERCHANT_PATTERN = r'\d{9,10}'
    
    # Orange Money merchant account format
    ORANGE_MONEY_MERCHANT_PATTERN = r'\d{9,10}'
    
    def __init__(self):
        pass
    
    def verify_deposit(
        self,
        receipt_upload,
        bank_statements: List[any],
        tolerance_days: int = 7
    ) -> Dict:
        """
        Verify that deposit exists in bank statements.
        
        Args:
            receipt_upload: PaymentProofUpload instance
            bank_statements: List of BankStatementEntry instances
            tolerance_days: Days to search before/after receipt date
        
        Returns:
            {
                "verified": bool,
                "matched_entry": BankStatementEntry | None,
                "match_confidence": float (0.0-1.0),
                "match_method": str,
                "discrepancies": list[str]
            }
        """
        from .models import BankStatementEntry
        
        if not receipt_upload.transaction_reference and not receipt_upload.uploaded_amount:
            return {
                "verified": False,
                "matched_entry": None,
                "match_confidence": 0.0,
                "match_method": "insufficient_data",
                "discrepancies": ["No transaction reference or amount provided"]
            }
        
        # Determine search date range
        search_start = receipt_upload.receipt_date or receipt_upload.created_at.date()
        search_start = search_start - timedelta(days=tolerance_days)
        search_end = (receipt_upload.receipt_date or receipt_upload.created_at.date()) + timedelta(days=tolerance_days)
        
        # Filter bank statements by date range
        relevant_statements = [
            stmt for stmt in bank_statements
            if search_start <= stmt.transaction_date <= search_end
        ]
        
        if not relevant_statements:
            return {
                "verified": False,
                "matched_entry": None,
                "match_confidence": 0.0,
                "match_method": "no_statements_in_range",
                "discrepancies": [f"No bank statements found between {search_start} and {search_end}"]
            }
        
        # Try to match by transaction reference first (most reliable)
        if receipt_upload.transaction_reference:
            matched = self._match_by_reference(
                receipt_upload.transaction_reference,
                relevant_statements
            )
            if matched:
                return {
                    "verified": True,
                    "matched_entry": matched,
                    "match_confidence": 0.95,
                    "match_method": "transaction_reference",
                    "discrepancies": []
                }
        
        # Try to match by amount and date (less reliable but still useful)
        if receipt_upload.uploaded_amount:
            matched = self._match_by_amount_and_date(
                receipt_upload.uploaded_amount,
                receipt_upload.receipt_date or receipt_upload.created_at.date(),
                relevant_statements,
                tolerance_days=tolerance_days
            )
            if matched:
                return {
                    "verified": True,
                    "matched_entry": matched["entry"],
                    "match_confidence": matched["confidence"],
                    "match_method": "amount_and_date",
                    "discrepancies": matched.get("discrepancies", [])
                }
        
        # No match found
        return {
            "verified": False,
            "matched_entry": None,
            "match_confidence": 0.0,
            "match_method": "no_match",
            "discrepancies": [
                f"Payment of {receipt_upload.uploaded_amount} "
                f"with reference '{receipt_upload.transaction_reference}' "
                f"not found in bank statements"
            ]
        }
    
    def _match_by_reference(
        self,
        transaction_reference: str,
        bank_statements: List[any]
    ) -> Optional[any]:
        """Match by transaction reference (exact or partial)."""
        ref_upper = transaction_reference.upper().strip()
        
        for stmt in bank_statements:
            # Check exact match
            if stmt.transaction_reference and stmt.transaction_reference.upper().strip() == ref_upper:
                return stmt
            
            # Check if reference appears in description
            if stmt.description and ref_upper in stmt.description.upper():
                return stmt
        
        return None
    
    def _match_by_amount_and_date(
        self,
        amount: Decimal,
        receipt_date,
        bank_statements: List[any],
        tolerance_days: int = 7,
        amount_tolerance: Decimal = Decimal("1.00")
    ) -> Optional[Dict]:
        """Match by amount and date (within tolerance)."""
        matches = []
        
        for stmt in bank_statements:
            # Check amount match (within tolerance)
            amount_diff = abs(stmt.amount - amount)
            if amount_diff > amount_tolerance:
                continue
            
            # Check date match (within tolerance)
            date_diff = abs((stmt.transaction_date - receipt_date).days)
            if date_diff > tolerance_days:
                continue
            
            # Calculate confidence (closer amounts and dates = higher confidence)
            amount_confidence = 1.0 - (float(amount_diff) / float(amount)) if amount > 0 else 0.0
            date_confidence = 1.0 - (date_diff / tolerance_days)
            confidence = (amount_confidence * 0.7) + (date_confidence * 0.3)
            
            matches.append({
                "entry": stmt,
                "confidence": confidence,
                "amount_diff": amount_diff,
                "date_diff": date_diff,
                "discrepancies": []
            })
        
        if not matches:
            return None
        
        # Return best match (highest confidence)
        return max(matches, key=lambda x: x["confidence"])
    
    def verify_mtn_momo_deposit(
        self,
        receipt_upload,
        mtn_momo_statements: List[any]
    ) -> Dict:
        """Verify MTN MoMo deposit (Cameroon-specific)."""
        # MTN MoMo transactions typically have format: MMXXXXXXXXX
        # or just numeric reference
        
        if not receipt_upload.transaction_reference:
            return {
                "verified": False,
                "matched_entry": None,
                "match_confidence": 0.0,
                "match_method": "no_reference",
                "discrepancies": ["No MTN MoMo transaction reference provided"]
            }
        
        # Normalize MTN MoMo reference (remove MM prefix if present)
        ref = receipt_upload.transaction_reference.upper().strip()
        if ref.startswith("MM"):
            ref = ref[2:]
        
        # Search in MTN MoMo statements
        for stmt in mtn_momo_statements:
            stmt_ref = stmt.transaction_reference or ""
            stmt_ref_normalized = stmt_ref.upper().strip()
            if stmt_ref_normalized.startswith("MM"):
                stmt_ref_normalized = stmt_ref_normalized[2:]
            
            if ref == stmt_ref_normalized or ref in stmt_ref_normalized:
                return {
                    "verified": True,
                    "matched_entry": stmt,
                    "match_confidence": 0.95,
                    "match_method": "mtn_momo_reference",
                    "discrepancies": []
                }
        
        return {
            "verified": False,
            "matched_entry": None,
            "match_confidence": 0.0,
            "match_method": "no_match",
            "discrepancies": [f"MTN MoMo transaction {receipt_upload.transaction_reference} not found"]
        }
    
    def verify_orange_money_deposit(
        self,
        receipt_upload,
        orange_money_statements: List[any]
    ) -> Dict:
        """Verify Orange Money deposit (Cameroon-specific)."""
        # Orange Money transactions typically have numeric references
        
        if not receipt_upload.transaction_reference:
            return {
                "verified": False,
                "matched_entry": None,
                "match_confidence": 0.0,
                "match_method": "no_reference",
                "discrepancies": ["No Orange Money transaction reference provided"]
            }
        
        ref = receipt_upload.transaction_reference.strip()
        
        # Search in Orange Money statements
        for stmt in orange_money_statements:
            stmt_ref = (stmt.transaction_reference or "").strip()
            
            if ref == stmt_ref or ref in stmt_ref:
                return {
                    "verified": True,
                    "matched_entry": stmt,
                    "match_confidence": 0.95,
                    "match_method": "orange_money_reference",
                    "discrepancies": []
                }
        
        return {
            "verified": False,
            "matched_entry": None,
            "match_confidence": 0.0,
            "match_method": "no_match",
            "discrepancies": [f"Orange Money transaction {receipt_upload.transaction_reference} not found"]
        }
