"""Wave S-A (v3.96.1 — 2026-05-26) — Bulk gradebook + rubric editor.

Teachers currently grade row-by-row. This kernel adds the bulk-entry path:

- ``parse_grade_value(raw, scale)`` — accepts the four conventions teachers
  paste in (percent, points-out-of-N, letter, 0–4 GPA) and normalizes them
  to a 0–100 percent.
- ``validate_bulk_grade_rows(rows, scale)`` — pure-function validator that
  collects per-row errors without short-circuiting.
- ``apply_bulk_grades(assessment_id, rows, db_runner=...)`` — single write
  path with an injectable runner for tests.
- Rubric editor: ``Rubric`` / ``Criterion`` / ``Level`` dataclasses +
  ``score_with_rubric(work, rubric)`` that maps per-criterion levels to a
  weighted total.

ZERO new migrations. The kernel is storage-agnostic — the caller persists
to whatever assessment row already exists in ``apps.evals``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation


# --- Grade scale + parsing ------------------------------------------------


@dataclass(frozen=True)
class GradeScale:
    kind: str  # "percent" | "points" | "letter" | "gpa4"
    max_points: Decimal = Decimal("100")


_LETTER_TO_PERCENT: dict[str, Decimal] = {
    "A+": Decimal("97"), "A": Decimal("93"), "A-": Decimal("90"),
    "B+": Decimal("87"), "B": Decimal("83"), "B-": Decimal("80"),
    "C+": Decimal("77"), "C": Decimal("73"), "C-": Decimal("70"),
    "D+": Decimal("67"), "D": Decimal("63"), "D-": Decimal("60"),
    "F": Decimal("50"),
}

_GPA_TO_PERCENT: dict[str, Decimal] = {
    "4.0": Decimal("95"), "3.7": Decimal("90"),
    "3.3": Decimal("87"), "3.0": Decimal("83"), "2.7": Decimal("80"),
    "2.3": Decimal("77"), "2.0": Decimal("73"), "1.7": Decimal("70"),
    "1.3": Decimal("67"), "1.0": Decimal("63"), "0.0": Decimal("50"),
}

_NUM_RE = re.compile(r"^(\d+(?:\.\d+)?)$")
_FRACTION_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)$")
_PERCENT_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*%$")


class GradeParseError(ValueError):
    pass


def parse_grade_value(raw: str, scale: GradeScale) -> Decimal:
    """Normalize ``raw`` to a 0–100 percent.

    Accepted formats:
    - ``"85"`` (number-only; interpreted under ``scale.kind``)
    - ``"85%"`` (explicit percent)
    - ``"17/20"`` (fraction — overrides scale)
    - ``"B+"`` (letter)
    - ``"3.7"`` (GPA on the 4.0 scale, only when scale.kind == "gpa4")
    """
    if raw is None:
        raise GradeParseError("missing")
    text = str(raw).strip()
    if not text:
        raise GradeParseError("missing")

    m = _FRACTION_RE.match(text)
    if m:
        num = Decimal(m.group(1))
        den = Decimal(m.group(2))
        if den == 0:
            raise GradeParseError("division_by_zero")
        return _clamp(num / den * Decimal("100"))

    m = _PERCENT_RE.match(text)
    if m:
        return _clamp(Decimal(m.group(1)))

    if scale.kind == "letter":
        letter = text.upper()
        if letter not in _LETTER_TO_PERCENT:
            raise GradeParseError("unknown_letter")
        return _LETTER_TO_PERCENT[letter]

    if scale.kind == "gpa4":
        if text in _GPA_TO_PERCENT:
            return _GPA_TO_PERCENT[text]
        raise GradeParseError("unknown_gpa")

    m = _NUM_RE.match(text)
    if m:
        try:
            value = Decimal(m.group(1))
        except InvalidOperation as exc:
            raise GradeParseError("invalid_number") from exc
        if scale.kind == "points":
            if scale.max_points <= 0:
                raise GradeParseError("invalid_scale_max")
            return _clamp(value / scale.max_points * Decimal("100"))
        # percent
        return _clamp(value)

    raise GradeParseError("unrecognized_format")


def _clamp(v: Decimal) -> Decimal:
    if v < 0:
        return Decimal("0")
    if v > 100:
        return Decimal("100")
    return v


# --- Bulk grade rows ------------------------------------------------------


@dataclass
class BulkGradeRow:
    student_id: int
    raw_value: str
    remarks: str = ""


@dataclass
class GradeRowError:
    student_id: int
    field: str
    reason: str
    raw_value: str = ""


@dataclass
class BulkGradeValidation:
    accepted: list[tuple[BulkGradeRow, Decimal]] = field(default_factory=list)
    errors: list[GradeRowError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    @property
    def accepted_count(self) -> int:
        return len(self.accepted)


def validate_bulk_grade_rows(
    rows: list[BulkGradeRow], scale: GradeScale,
) -> BulkGradeValidation:
    result = BulkGradeValidation()
    seen_students: set[int] = set()
    for row in rows:
        if row.student_id in seen_students:
            result.errors.append(GradeRowError(
                student_id=row.student_id, field="student_id",
                reason="duplicate", raw_value=str(row.student_id),
            ))
            continue
        seen_students.add(row.student_id)
        try:
            normalized = parse_grade_value(row.raw_value, scale)
        except GradeParseError as exc:
            result.errors.append(GradeRowError(
                student_id=row.student_id, field="raw_value",
                reason=str(exc), raw_value=row.raw_value,
            ))
            continue
        result.accepted.append((row, normalized))
    return result


@dataclass
class BulkGradeApplyResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[dict] = field(default_factory=list)


def apply_bulk_grades(
    *,
    assessment_id: int,
    rows: list[BulkGradeRow],
    scale: GradeScale,
    db_runner=None,
) -> BulkGradeApplyResult:
    """Run validation + write. Validation-fail short-circuits with no writes."""
    validation = validate_bulk_grade_rows(rows, scale)
    if not validation.is_valid:
        return BulkGradeApplyResult(
            errors=[
                {"student_id": e.student_id, "field": e.field, "reason": e.reason}
                for e in validation.errors
            ],
        )
    runner = db_runner or _default_grade_runner
    return runner(
        assessment_id=assessment_id,
        accepted=validation.accepted,
    )


def _default_grade_runner(
    *, assessment_id: int, accepted: list[tuple[BulkGradeRow, Decimal]],
) -> BulkGradeApplyResult:
    # Lazy import — kernel testable as SimpleTestCase without ORM.
    try:
        from apps.evals.models import StudentEvaluation  # type: ignore
    except Exception:  # noqa: BLE001
        return BulkGradeApplyResult(errors=[{"reason": "evals_model_unavailable"}])

    result = BulkGradeApplyResult()
    for row, normalized in accepted:
        try:
            # tenant-isolation-allow: bulk-gradebook-evaluation-confined-to-assessment-scope
            _, created = StudentEvaluation.objects.update_or_create(
                assessment_id=assessment_id,
                student_id=row.student_id,
                defaults={"score_percent": normalized, "remarks": row.remarks},
            )
            if created:
                result.created += 1
            else:
                result.updated += 1
        except Exception as exc:  # noqa: BLE001
            result.errors.append({
                "student_id": row.student_id, "reason": str(exc)[:240],
            })
    return result


# --- Rubric editor --------------------------------------------------------


@dataclass(frozen=True)
class Level:
    """One row in a rubric criterion (e.g. 'Exceeds expectations')."""
    key: str
    label: str
    points: Decimal
    descriptor: str = ""


@dataclass(frozen=True)
class Criterion:
    key: str
    label: str
    weight: Decimal  # e.g. Decimal("0.30") for 30% of the total
    levels: tuple[Level, ...]


@dataclass(frozen=True)
class Rubric:
    rubric_id: str
    name: str
    criteria: tuple[Criterion, ...]


class RubricValidationError(ValueError):
    pass


def validate_rubric(rubric: Rubric) -> None:
    if not rubric.rubric_id or not rubric.name:
        raise RubricValidationError("rubric_id_and_name_required")
    if not rubric.criteria:
        raise RubricValidationError("at_least_one_criterion_required")
    seen_keys: set[str] = set()
    weight_sum = Decimal("0")
    for criterion in rubric.criteria:
        if not criterion.key:
            raise RubricValidationError("criterion_key_required")
        if criterion.key in seen_keys:
            raise RubricValidationError(f"duplicate_criterion_key:{criterion.key}")
        seen_keys.add(criterion.key)
        if not criterion.levels:
            raise RubricValidationError(
                f"criterion_must_have_levels:{criterion.key}"
            )
        if criterion.weight < 0:
            raise RubricValidationError(
                f"criterion_weight_negative:{criterion.key}"
            )
        weight_sum += criterion.weight
        max_pts = max(level.points for level in criterion.levels)
        if max_pts <= 0:
            raise RubricValidationError(
                f"criterion_max_points_must_be_positive:{criterion.key}"
            )
    # Allow weights to sum to 0.99–1.01 to tolerate rounding.
    if not (Decimal("0.99") <= weight_sum <= Decimal("1.01")):
        raise RubricValidationError(
            f"criterion_weights_must_sum_to_1_got:{weight_sum}"
        )


@dataclass
class RubricScoringResult:
    rubric_id: str
    per_criterion: dict[str, Decimal] = field(default_factory=dict)
    weighted_total_percent: Decimal = Decimal("0")
    errors: list[str] = field(default_factory=list)


def score_with_rubric(
    *,
    rubric: Rubric,
    selections: dict[str, str],  # criterion_key → level_key
) -> RubricScoringResult:
    """Compute the weighted total from a teacher's per-criterion level picks."""
    validate_rubric(rubric)
    result = RubricScoringResult(rubric_id=rubric.rubric_id)
    for criterion in rubric.criteria:
        level_key = selections.get(criterion.key)
        if level_key is None:
            result.errors.append(
                f"missing_selection_for_criterion:{criterion.key}"
            )
            continue
        level = next((l for l in criterion.levels if l.key == level_key), None)
        if level is None:
            result.errors.append(
                f"unknown_level_for_criterion:{criterion.key}:{level_key}"
            )
            continue
        max_pts = max(l.points for l in criterion.levels)
        percent = (level.points / max_pts) * Decimal("100")
        result.per_criterion[criterion.key] = percent
        result.weighted_total_percent += percent * criterion.weight
    if result.errors:
        result.weighted_total_percent = Decimal("0")
    return result
