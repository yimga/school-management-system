"""Cashless campus POS checkout + allergen sale-block (Wave C — campus commerce).

Turns a campus device into a cashless till: resolve the student from a scanned
credential (QR id / RFID badge → ``student_code``, or an explicit id), enforce
the **allergen barrier** (refuse a sale whose item matches a student allergen),
debit the student's campus wallet (``schoolops.MealPlanBalance``) atomically, and
record each line as a ``schoolops.PosSaleLine`` (now student-linked + idempotent).

Decimal-safe throughout (never ``float`` on money). Idempotent per
``idempotency_key`` so a retried scan never double-charges — enforced by the
``uniq_possaleline_school_idem`` partial unique index, not by the pre-insert
read, which two concurrent replays both pass. Allergen enforcement
honours the tenant's POS wizard setting and is on by default (safety-first).
Allergen matching folds plurals and compounds (see :func:`_term_matches_token`)
because canteen item names are written as "Peanuts" and "Chocolate Milkshake",
not as the bare allergen word.

See docs/GLOCAL_SOVEREIGNTY_PLAN.md (Wave C) and register rows
``cashless-campus-pos`` / ``allergen-barrier-pos``.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from django.db import IntegrityError, transaction

# School.settings flat key written by the POS wizard's allergen step.
ALLERGEN_RULES_SETTING = "wizards.cashless_campus_pos.allergen_dietary_rules"

# Tokens that are not themselves allergens — dropped before matching.
_ALLERGEN_STOPWORDS = frozenset(
    {
        "allergy", "allergies", "allergic", "severe", "mild", "moderate",
        "reaction", "intolerance", "intolerant", "and", "the", "for",
        "with", "none", "nil", "history", "student", "note", "notes",
        # Directives a nurse writes around the allergen, never allergens
        # themselves — they would only ever produce false blocks.
        "avoid", "avoids", "all", "any",
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
        school_id=student.school_id,
        student_id=student.pk,
        record_type__icontains="allerg",
    ):
        terms |= _tokenize(row.notes)
    if hasattr(student, "tags"):
        for tag in student.tags.all():
            name = getattr(tag, "name", "") or ""
            if "allerg" in name.lower():
                terms |= _tokenize(name)
    return terms


def _singular(word: str) -> str:
    """Crude plural fold so "peanuts" and "peanut" compare equal."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("es") and len(word) > 4:
        return word[:-2]
    if word.endswith("s") and len(word) > 3:
        return word[:-1]
    return word


def _term_matches_token(term: str, token: str) -> bool:
    """True when an allergen term matches one token of a menu-item label.

    Whole-token equality misses the two ways a canteen actually names food:
    plurals ("Peanuts") and compounds ("Milkshake"). So we fold plurals, accept
    either side as a prefix of the other, and allow an interior substring only
    when the shorter side is 4+ characters. That last floor is not cosmetic —
    a 3-letter fragment matches far too much ("raw" sits inside "strawberry"),
    and a barrier that blocks the whole menu gets switched off by the canteen,
    which is the worst outcome for the child it exists to protect.
    """
    a, b = _singular(term), _singular(token)
    if a == b or a.startswith(b) or b.startswith(a):
        return True
    if len(a) >= 4 and a in b:
        return True
    if len(b) >= 4 and b in a:
        return True
    return False


def allergen_conflict(student, item_label: str) -> str | None:
    """Return the first student-allergen term present in the item label, else None."""
    label_tokens = _tokenize(item_label)
    for term in sorted(student_allergen_terms(student)):
        if any(_term_matches_token(term, tok) for tok in label_tokens):
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


def _prior_sale_line_ids(school_id, key: str) -> list:
    """Ids already committed under this idempotency key, for this school."""
    from apps.schoolops.models import PosSaleLine

    return list(
        PosSaleLine.objects.filter(
            school_id=school_id, idempotency_key=key
        ).values_list("id", flat=True)
    )


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
        # Read the dedupe inside the transaction, not before it: a retried
        # scan from a flaky till hits two workers at once and a pre-transaction
        # read lets both of them through. The read still cannot see an
        # uncommitted sibling, so the real guarantee is the partial unique
        # index below — this is only the cheap path for a replay that arrives
        # after the first one committed.
        if key:
            prior = _prior_sale_line_ids(school_id, key)
            if prior:
                return {"ok": True, "dedup": True, "sale_line_ids": prior}
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
        try:
            # Savepoint so the IntegrityError below does not poison the outer
            # transaction (on PostgreSQL a failed statement aborts it).
            with transaction.atomic():
                for seq, it in enumerate(norm_items):
                    line = PosSaleLine.objects.create(
                        school_id=school_id,
                        student_id=student.pk,
                        item_label=it["label"],
                        quantity=it["quantity"],
                        unit_price=it["unit_price"],
                        payment_method=payment_method,
                        idempotency_key=key,
                        idempotency_seq=seq,
                        recorded_by_id=cashier_user_id,
                        notes="Cashless campus POS",
                    )
                    sale_ids.append(line.id)
        except IntegrityError:
            # uniq_possaleline_school_idem fired: a concurrent replay of this
            # same scan committed while we were between the dedupe read and
            # the insert. That sale stands; ours is a duplicate and must NOT
            # debit the wallet a second time.
            if not key:
                raise
            # Re-read directly rather than through _prior_sale_line_ids: the
            # winner is committed by now, so this is a different question from
            # the pre-insert check above.
            return {
                "ok": True,
                "dedup": True,
                "sale_line_ids": list(
                    PosSaleLine.objects.filter(
                        school_id=school_id, idempotency_key=key
                    ).values_list("id", flat=True)
                ),
            }
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
