"""Cashless campus POS checkout + allergen sale-block (Wave C — campus commerce).

Turns a campus device into a cashless till: resolve the student from a scanned
credential (QR id / RFID badge → ``student_code``, or an explicit id), enforce
the **allergen barrier** (refuse a sale whose item matches a student allergen),
debit the student's campus wallet (``schoolops.MealPlanBalance``) atomically, and
record each line as a ``schoolops.PosSaleLine`` (now student-linked + idempotent).

Decimal-safe throughout (never ``float`` on money). Idempotent per
``idempotency_key`` so a retried scan never double-charges. Allergen enforcement
honours the tenant's POS wizard setting and is on by default (safety-first).

See docs/GLOCAL_SOVEREIGNTY_PLAN.md (Wave C) and register rows
``cashless-campus-pos`` / ``allergen-barrier-pos``.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from django.db import transaction

# School.settings flat key written by the POS wizard's allergen step.
ALLERGEN_RULES_SETTING = "wizards.cashless_campus_pos.allergen_dietary_rules"

# Tokens that are not themselves allergens — dropped before matching.
_ALLERGEN_STOPWORDS = frozenset(
    {
        "allergy", "allergies", "allergic", "severe", "mild", "moderate",
        "reaction", "intolerance", "intolerant", "and", "the", "for",
        "with", "none", "nil", "history", "student", "note", "notes",
    }
)

_MIN_TOKEN_LEN = 3


def _tokenize(text: Any) -> set[str]:
    """Lower-cased alpha tokens of length >= 3, minus allergen stopwords."""
    raw = re.split(r"[^a-z]+", str(text or "").lower())
    return {w for w in raw if len(w) >= _MIN_TOKEN_LEN and w not in _ALLERGEN_STOPWORDS}


def resolve_student_for_credential(school_id, *, student_id=None, credential=None):
    """Resolve a StudentProfile in this school by explicit id or scanned code."""
    from apps.people.models import StudentProfile

    qs = StudentProfile.objects.filter(school_id=school_id)
    if student_id:
        return qs.filter(pk=student_id).first()
    cred = str(credential or "").strip()
    if cred:
        return qs.filter(student_code=cred).first()
    return None


def student_allergen_terms(student) -> set[str]:
    """Allergen keywords for a student, from HealthRecord allergy rows + Allergy tags."""
    from apps.schoolops.models import HealthRecord

    if student is None:
        return set()
    terms: set[str] = set()
    for row in HealthRecord.objects.filter(
        student_id=student.pk, record_type__icontains="allerg"
    ):
        terms |= _tokenize(row.notes)
    if hasattr(student, "tags"):
        for tag in student.tags.all():
            name = getattr(tag, "name", "") or ""
            if "allerg" in name.lower():
                terms |= _tokenize(name)
    return terms


def allergen_conflict(student, item_label: str) -> str | None:
    """Return the first student-allergen term present in the item label, else None."""
    label_tokens = _tokenize(item_label)
    for term in student_allergen_terms(student):
        if term in label_tokens:
            return term
    return None


def _to_decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _normalize_items(items: Iterable[dict]) -> list[dict]:
    out: list[dict] = []
    for it in items or []:
        label = str(it.get("label") or it.get("item_label") or "").strip()
        if not label:
            continue
        qty = it.get("quantity", 1)
        try:
            qty = max(1, int(qty))
        except (TypeError, ValueError):
            qty = 1
        out.append(
            {"label": label[:255], "unit_price": _to_decimal(it.get("unit_price")), "quantity": qty}
        )
    return out


def _allergen_enforced(school_id, override) -> bool:
    if override is not None:
        return bool(override)
    from apps.schools.models import School

    school = School.objects.filter(pk=school_id).first()
    blob = (getattr(school, "settings", None) or {}) if school else {}
    val = blob.get(ALLERGEN_RULES_SETTING)
    if isinstance(val, dict):
        return bool(val.get("enabled", val.get("enable", True)))
    if val is None:
        return True  # safety-first default: block until explicitly disabled
    return bool(val)


def checkout(
    *,
    school_id,
    student,
    items: Iterable[dict],
    cashier_user_id=None,
    payment_method: str = "account",
    enforce_allergen: bool | None = None,
    idempotency_key: str = "",
) -> dict[str, Any]:
    """Run a cashless POS checkout. See module docstring for guarantees."""
    from apps.schoolops.models import MealPlanBalance, PosSaleLine

    if student is None:
        return {"ok": False, "error": "Unknown student / credential."}
    norm_items = _normalize_items(items)
    if not norm_items:
        return {"ok": False, "error": "No items to charge."}

    key = (idempotency_key or "").strip()[:128]
    if key:
        prior = list(
            PosSaleLine.objects.filter(school_id=school_id, idempotency_key=key).values_list(
                "id", flat=True
            )
        )
        if prior:
            return {"ok": True, "dedup": True, "sale_line_ids": prior}

    if _allergen_enforced(school_id, enforce_allergen):
        for it in norm_items:
            term = allergen_conflict(student, it["label"])
            if term:
                return {
                    "ok": False,
                    "blocked": True,
                    "reason": f"Allergen block: '{it['label']}' matches student allergen '{term}'.",
                }

    total = sum((it["unit_price"] * it["quantity"] for it in norm_items), Decimal("0"))

    with transaction.atomic():
        wallet = (
            MealPlanBalance.objects.select_for_update()
            .filter(school_id=school_id, student_id=student.pk, meal_plan__isnull=True)
            .first()
        )
        if wallet is None:
            created = MealPlanBalance.objects.create(
                school_id=school_id,
                student_id=student.pk,
                meal_plan=None,
                balance=Decimal("0.00"),
            )
            wallet = MealPlanBalance.objects.select_for_update().get(pk=created.pk)
        if wallet.status != "active":
            return {"ok": False, "blocked": True, "reason": f"Wallet is {wallet.status}."}
        if payment_method == "account" and wallet.balance < total:
            return {
                "ok": False,
                "insufficient": True,
                "reason": "Insufficient wallet balance.",
                "balance": str(wallet.balance),
                "required": str(total),
            }
        sale_ids: list[int] = []
        for it in norm_items:
            line = PosSaleLine.objects.create(
                school_id=school_id,
                student_id=student.pk,
                item_label=it["label"],
                quantity=it["quantity"],
                unit_price=it["unit_price"],
                payment_method=payment_method,
                idempotency_key=key,
                recorded_by_id=cashier_user_id,
                notes="Cashless campus POS",
            )
            sale_ids.append(line.id)
        if payment_method == "account":
            wallet.balance = wallet.balance - total
            wallet.save(update_fields=["balance", "updated_at"])

    return {
        "ok": True,
        "sale_line_ids": sale_ids,
        "charged": str(total),
        "new_balance": str(wallet.balance),
        "payment_method": payment_method,
    }
