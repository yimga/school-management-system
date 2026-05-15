"""AI categorisation for finance — assigns a category + payer hint to
unmatched bank statement entries.

Used by ``BankStatementImportService._link_or_create_suspense`` when no
deterministic reference match (student ID, invoice number) is found. The
helper returns a structured proposal the caller can store on the suspense
record so an operator can accept/override in the reconciliation UI.

Graceful degradation: when AI is disabled the helper returns ``None`` and
the suspense flow continues exactly as today (manual operator review).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# Stable categories the operator UI knows how to render. Add by extending
# this list AND the suspense reconciliation template's filter dropdown.
SUPPORTED_CATEGORIES: tuple[str, ...] = (
    "tuition_fee_payment",
    "transport_fee_payment",
    "cafeteria_topup",
    "hostel_fee_payment",
    "uniform_purchase",
    "library_fine",
    "donation",
    "refund_outbound",
    "supplier_payout",
    "salary_payout",
    "bank_charge",
    "transfer_internal",
    "unknown",
)


@dataclass
class FinanceCategoryProposal:
    category: str
    confidence: float
    payer_hint: str
    reasoning: str
    tier: str


def propose_category(
    *,
    school: Any | None,
    description: str,
    amount: Decimal | float | int,
    transaction_type: str,
    payer_phone: str = "",
    payer_name: str = "",
) -> FinanceCategoryProposal | None:
    """Ask the gateway for a category guess on an unmatched deposit.

    Returns ``None`` when AI is disabled, the call fails, or the model
    couldn't return a parseable answer. Callers MUST treat ``None`` as
    "no categorisation" and fall back to manual review.
    """
    from services.ai_helpers import invoke_json_task, looks_like_pii

    description = (description or "").strip()
    if not description:
        return None

    sensitivity = "high_pii" if looks_like_pii(description, payer_phone, payer_name) else "standard"
    prompt = _build_prompt(description, amount, transaction_type, payer_phone, payer_name)

    parsed = invoke_json_task(
        school=school,
        task_type_name="DOC_CLASSIFY",
        prompt=prompt,
        prompt_type="finance.statement_categorizer",
        content_sensitivity=sensitivity,
    )
    if parsed is None:
        return None

    obj, meta = parsed
    category = str(obj.get("category", "")).strip().lower()
    if category not in SUPPORTED_CATEGORIES:
        return None

    confidence = _clip(obj.get("confidence"))
    return FinanceCategoryProposal(
        category=category,
        confidence=confidence,
        payer_hint=str(obj.get("payer_hint", "")).strip()[:120],
        reasoning=str(obj.get("reasoning", "")).strip()[:280],
        tier=str(meta.get("tier", "unknown")),
    )


def _build_prompt(
    description: str,
    amount: Decimal | float | int,
    transaction_type: str,
    payer_phone: str,
    payer_name: str,
) -> str:
    return (
        "You are a finance assistant for a school management platform.\n"
        "Given a bank statement entry, classify it into one of the allowed categories.\n"
        "Return JSON ONLY. If unsure, set category=\"unknown\" with low confidence.\n\n"
        f"Allowed categories: {list(SUPPORTED_CATEGORIES)}\n"
        f"Description: {description!r}\n"
        f"Amount: {amount}\n"
        f"Transaction type: {transaction_type}\n"
        f"Payer phone (may be empty): {payer_phone!r}\n"
        f"Payer name (may be empty): {payer_name!r}\n\n"
        'Return JSON exactly: {"category": "<one of allowed>", "confidence": <0..1>, '
        '"payer_hint": "<a short text guess at who paid, or empty>", '
        '"reasoning": "<one sentence>"}'
    )


def _clip(raw: Any) -> float:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))
