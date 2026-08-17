import uuid
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

from apps.academics.models import AcademicYear, Term, SubjectAssignment

from apps.people.models import TeacherProfile, StudentProfile
from apps.accounts.models import User
from apps.accounts.validators import validate_evidence_file, validate_file_size_20mb


# Canonical letter-grade bands + score scale per grading_scale choice. The bands are
# the SCALE's bands, not one country's — picking "percentage" yields 80/70/60/50, "gpa_4_0"
# yields GPA bands, etc. This is the SoT the pre_save realignment + any seeding reads.
GRADING_SCALE_BANDS: dict[str, dict[str, float]] = {
    "numeric_0_20": {"a": 18, "b": 16, "c": 14, "d": 10, "e": 0, "score_scale": 20},
    "letter_a_e": {"a": 18, "b": 16, "c": 14, "d": 10, "e": 0, "score_scale": 20},
    "gpa_4_0": {"a": 3.5, "b": 3.0, "c": 2.0, "d": 1.0, "e": 0, "score_scale": 4},
    "percentage": {"a": 80, "b": 70, "c": 60, "d": 50, "e": 0, "score_scale": 100},
    # Post-Soviet 1–5 (5=excellent … 1=poor), pass at 3. Fits the 5-band model on a
    # 0–5 axis, so GradeConverter computes letters/GPA/% with no special casing.
    "numeric_1_5": {"a": 4.5, "b": 4, "c": 3.5, "d": 3, "e": 0, "score_scale": 5},
    # Scales whose true grade label lives in EXTENDED_GRADE_BANDS. These coarse A–E
    # tiers exist only so score_scale + the legacy single-char letter_grade still work;
    # the displayed grade (A1…F9 / Pass-Fail / descriptor) comes from band_label.
    "waec_letter": {"a": 75, "b": 65, "c": 55, "d": 50, "e": 0, "score_scale": 100},
    "pass_fail": {"a": 50, "b": 50, "c": 50, "d": 50, "e": 0, "score_scale": 100},
    "qualitative_pd": {"a": 85, "b": 70, "c": 55, "d": 50, "e": 0, "score_scale": 100},
    # T-score is cohort-RELATIVE (the defining T = 50 + 10·(x−mean)/sd is computed by
    # cohort_t_scores, not from one raw score). These coarse bands only drive score_scale
    # + the single-score letter fallback; the T value comes from the cohort helper.
    "standard_score_t": {"a": 70, "b": 60, "c": 50, "d": 40, "e": 0, "score_scale": 100},
    "uk_gcse_9_1": {"a": 7, "b": 5, "c": 4, "d": 3, "e": 1, "score_scale": 9},
    "ib_1_7": {"a": 6, "b": 5, "c": 4, "d": 3, "e": 1, "score_scale": 7},
    "german_1_6": {"a": 1.5, "b": 2.5, "c": 3.5, "d": 4.5, "e": 5.5, "score_scale": 6},
    "cbse_10": {"a": 9, "b": 8, "c": 7, "d": 6, "e": 0, "score_scale": 10},
    "french_0_20": {"a": 18, "b": 16, "c": 14, "d": 10, "e": 0, "score_scale": 20},
    "us_letter": {"a": 90, "b": 80, "c": 70, "d": 60, "e": 0, "score_scale": 100},
}

# Field defaults for the numeric_0_20 scale — used to detect "thresholds untouched".
_NUMERIC_0_20_DEFAULT_BANDS = (18.0, 16.0, 14.0, 10.0, 0.0)

# Rich band labels for scales whose grade representation does NOT fit the 5-band A–E
# numeric model: WAEC's 9 lettered bands, binary Pass/Fail, and qualitative descriptors.
# Each ``bands`` is (label, min_score) on the scale's 0..score_scale axis, DESCENDING.
# The coarse A–E tier in GRADING_SCALE_BANDS still drives score_scale + the legacy
# single-char ``Evaluation.letter_grade`` (backward-compatible); the rich label here is
# DERIVED on demand (resolve_extended_band_label / GradeConverter.band_label), so no
# schema change to the high-volume Evaluation table is needed.
EXTENDED_GRADE_BANDS: dict[str, dict] = {
    "waec_letter": {
        "score_scale": 100,
        "kind": "letter",
        "bands": [
            ("A1", 75), ("B2", 70), ("B3", 65), ("C4", 60), ("C5", 55),
            ("C6", 50), ("D7", 45), ("E8", 40), ("F9", 0),
        ],
    },
    "pass_fail": {
        "score_scale": 100,
        "kind": "binary",
        "bands": [("Pass", 50), ("Fail", 0)],
    },
    "qualitative_pd": {
        "score_scale": 100,
        "kind": "qualitative",
        "bands": [
            ("Exceeding Expectations", 85),
            ("Meeting Expectations", 70),
            ("Approaching Expectations", 50),
            ("Beginning", 0),
        ],
    },
    # UK GCSE 9–1: scored on the 1–9 grade axis (score_scale=9), 9 best … 1 worst.
    # Each whole grade is its own band (full 9…1), so a "6" displays "6", not a
    # collapsed "4". DESCENDING by min_score like every other ascending-direction scale.
    "uk_gcse_9_1": {
        "score_scale": 9,
        "kind": "numeric",
        "bands": [
            ("9", 9), ("8", 8), ("7", 7), ("6", 6), ("5", 5),
            ("4", 4), ("3", 3), ("2", 2), ("1", 1),
        ],
    },
    # IB Diploma subject grade: 1–7 axis (score_scale=7), 7 best … 1 worst. Full
    # whole-grade bands (7…1) so a "5" shows "5" rather than a collapsed lower band.
    "ib_1_7": {
        "score_scale": 7,
        "kind": "numeric",
        "bands": [
            ("7", 7), ("6", 6), ("5", 5), ("4", 4),
            ("3", 3), ("2", 2), ("1", 1),
        ],
    },
    # CBSE board letter grades on the 0–10 grade-point axis (score_scale=10, the
    # registry's cbse_10 range). A1=10 … D=4 are the canonical CBSE grade points; the
    # two failing tiers E1/E2 sit below the pass mark (D, GP 4). DESCENDING (10 best).
    "cbse_10": {
        "score_scale": 10,
        "kind": "letter",
        "bands": [
            ("A1", 10), ("A2", 9), ("B1", 8), ("B2", 7), ("C1", 6),
            ("C2", 5), ("D", 4), ("E1", 2), ("E2", 0),
        ],
    },
    # German 1–6 is INVERTED: 1 (sehr gut) is best, 6 (ungenügend) is worst, so a
    # LOWER score is a better grade — the only extended family that does not read
    # "higher score ⇒ higher band". ``direction: ascending`` flips resolve_extended_band_label
    # to "value <= max_score" semantics over bands ordered worst→best. Boundaries are the
    # standard rounding model for German averages (1: ≤1.49, 2: ≤2.49 … 6: ≤6.0). Pass at 4.
    "german_1_6": {
        "score_scale": 6,
        "kind": "numeric",
        "direction": "ascending",  # lower score = better grade
        # Ordered BEST→WORST by ceiling (like the descending families list best first),
        # each pair is (label, max_score) — the inclusive UPPER bound of that grade.
        "bands": [
            ("1", 1.49), ("2", 2.49), ("3", 3.49),
            ("4", 4.49), ("5", 5.49), ("6", 6.0),
        ],
    },
    # Francophone "note sur 20" mentions (Cameroon / France / Senegal): a 0–20
    # score reads as a French mention, never an A–E letter. Descending — return
    # the first band the value clears (value >= min). The anglophone numeric_0_20
    # scale deliberately stays A–E (absent here ⇒ GradeConverter.numeric_to_letter),
    # so bilingual schools keep both conventions on the SAME 0–20 axis.
    "french_0_20": {
        "score_scale": 20,
        "kind": "mention",
        "bands": [
            ("Très bien", 16),
            ("Bien", 14),
            ("Assez bien", 12),
            ("Passable", 10),
            ("Insuffisant", 0),
        ],
    },
}


def default_bands_for_scale(scale: str) -> dict[str, float]:
    """Letter-grade bands (+ score_scale) for a grading_scale choice; numeric_0_20 default."""
    return GRADING_SCALE_BANDS.get(scale) or GRADING_SCALE_BANDS["numeric_0_20"]


def resolve_extended_band_label(scale: str, score) -> Optional[str]:
    """Rich band label for a non-5-band scale, else None.

    Covers the world-scale families whose grade label does not fit the ordinary
    5-band A–E numeric model: WAEC (A1…F9), Pass/Fail, qualitative descriptors,
    UK GCSE 9–1, IB 1–7, CBSE A1–E2, and German 1–6.

    Direction matters. Most scales are "higher score ⇒ better band" (``direction``
    absent / ``"descending"``): bands are listed best→worst by ``min_score`` and we
    return the first band the value clears (``value >= min_score``), flooring at the
    lowest band. German 1–6 is INVERTED (``direction == "ascending"`` — a LOWER score
    is the BETTER grade): its bands are listed worst→best by ``max_score`` and we
    return the first band whose ceiling the value is within (``value <= max_score``),
    capping at the worst band.

    Returns None for scales that use the ordinary 5-band A–E model (callers fall back
    to GradeConverter.numeric_to_letter). Never raises — an out-of-range score yields
    the boundary band on the appropriate side.
    """
    spec = EXTENDED_GRADE_BANDS.get(scale)
    if not spec or score is None:
        return None
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    bands = spec["bands"]
    if spec.get("direction") == "ascending":
        # Inverted scales (German 1–6): bands ordered best→worst by ceiling; a lower
        # score is a better grade, so return the first band whose ceiling contains the
        # value (the best band's ceiling also floors tiny/negative scores to the best
        # grade). A value above the worst ceiling caps at the worst (last) band.
        for band_label, max_score in bands:
            if value <= float(max_score):
                return band_label
        return bands[-1][0]  # above the worst ceiling ⇒ worst band
    label = bands[-1][0]  # lowest band is the floor
    for band_label, min_score in bands:
        if value >= float(min_score):
            return band_label
    return label


def _apply_scale_consistent_bands(instance) -> None:
    """On create, align grade thresholds + score_scale to the chosen grading_scale.

    Only acts when (a) it's an insert, (b) a NON-default scale is chosen, and (c) the
    thresholds are still the numeric_0_20 field defaults — so a school picking "percentage"
    is scored on 80/70/60/50 instead of Cameroon's 0–20 bands. Never clobbers thresholds a
    caller set explicitly, and leaves the numeric_0_20 default untouched (backward-compatible).
    """
    state = getattr(instance, "_state", None)
    if state is None or not getattr(state, "adding", False):
        return
    scale = getattr(instance, "grading_scale", "") or ""
    if scale == "numeric_0_20" or scale not in GRADING_SCALE_BANDS:
        return

    def _close(a, b):
        try:
            return abs(float(a) - float(b)) < 0.001
        except (TypeError, ValueError):
            return False

    current = (
        instance.grade_a_min,
        instance.grade_b_min,
        instance.grade_c_min,
        instance.grade_d_min,
        instance.grade_e_min,
    )
    if not all(_close(c, d) for c, d in zip(current, _NUMERIC_0_20_DEFAULT_BANDS)):
        return  # thresholds were set explicitly — respect them
    bands = default_bands_for_scale(scale)
    instance.grade_a_min = Decimal(str(bands["a"]))
    instance.grade_b_min = Decimal(str(bands["b"]))
    instance.grade_c_min = Decimal(str(bands["c"]))
    instance.grade_d_min = Decimal(str(bands["d"]))
    instance.grade_e_min = Decimal(str(bands["e"]))
    if int(getattr(instance, "score_scale", 20) or 20) == 20:
        instance.score_scale = int(bands["score_scale"])


class AssessmentWeights(models.Model):
    """Weighting configuration for evaluation components.

    Cameroon schools commonly use continuous assessment + exams.
    Technical schools may also include Practical/TP and Mock exams.

    This model lets you define weights at two levels:
    - school-wide for an academic year (classroom = NULL)
    - per-classroom override (classroom = ...)

    We keep it in the evals app because it drives score computation.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="assessment_weights",
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="assessment_weights"
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assessment_weights",
        help_text="Optional term-specific override. Leave blank for full-year defaults.",
    )
    # Optional per-classroom override. We avoid importing Classroom directly to prevent circular imports.
    classroom = models.ForeignKey(
        "academics.Classroom",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="assessment_weights",
    )

    # Percent weights (0..100). Defaults are a common pattern: 20/20/60.
    seq1_weight = models.PositiveSmallIntegerField(default=20)
    seq2_weight = models.PositiveSmallIntegerField(default=20)
    exam_weight = models.PositiveSmallIntegerField(default=60)
    mock_weight = models.PositiveSmallIntegerField(default=0)
    practical_weight = models.PositiveSmallIntegerField(default=0)

    score_scale = models.PositiveSmallIntegerField(default=20)

    # Grade thresholds for letter conversion. These field defaults are the bands for
    # the numeric_0_20 scale (the model's default grading_scale). When a row is created
    # with a DIFFERENT grading_scale and the thresholds are left at these defaults, a
    # pre_save receiver realigns them to that scale's bands (see GRADING_SCALE_BANDS) so
    # a percentage / GPA school is NOT scored on 0–20 bands. Never clobbers explicit bands.
    grade_a_min = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=18.0,
        help_text="Minimum score for A",
    )
    grade_b_min = models.DecimalField(max_digits=5, decimal_places=2, default=16.0)
    grade_c_min = models.DecimalField(max_digits=5, decimal_places=2, default=14.0)
    grade_d_min = models.DecimalField(max_digits=5, decimal_places=2, default=10.0)
    grade_e_min = models.DecimalField(max_digits=5, decimal_places=2, default=0.0)

    # NEW: Grading scale & locale configuration
    grading_scale = models.CharField(
        max_length=50,
        choices=[
            ("numeric_0_20", "Numeric 0–20 (Cameroon Francophone)"),
            ("letter_a_e", "Letters A–E (Cameroon Anglophone)"),
            ("gpa_4_0", "GPA 4.0 Scale"),
            ("percentage", "Percentage 0–100"),
            ("numeric_1_5", "Numeric 1–5 (Post-Soviet)"),
            ("waec_letter", "WAEC letter bands (A1–F9)"),
            ("pass_fail", "Pass / Fail"),
            ("qualitative_pd", "Qualitative descriptors"),
            ("standard_score_t", "T-score (East Asia)"),
            ("uk_gcse_9_1", "UK GCSE 9–1"),
            ("ib_1_7", "IB 1–7"),
            ("german_1_6", "German 1–6"),
            ("cbse_10", "CBSE 10-point"),
            ("french_0_20", "French 0–20"),
            ("us_letter", "US letter A–F"),
        ],
        default="numeric_0_20",
    )
    # Local-first (2026-06-23): default region is GLOBAL, not a single country. This
    # field is descriptive metadata only (not consumed by grade computation — the
    # thresholds + grading_scale drive the math), so flipping the default is grade-safe
    # and stops new tenants worldwide being labelled "Cameroon Anglophone" by default.
    region = models.CharField(
        max_length=50,
        choices=[
            ("cameroon_anglophone", "Cameroon Anglophone"),
            ("cameroon_francophone", "Cameroon Francophone"),
            ("global", "Global/Other"),
        ],
        default="global",
    )

    @classmethod
    def get_for(cls, academic_year, classroom=None, term=None):
        # Priority: classroom+term, classroom, term, year only.
        if academic_year is None:
            return cls()

        if classroom is not None and term is not None:
            match = cls.objects.filter(
                academic_year=academic_year,
                classroom=classroom,
                term=term,
            ).first()
            if match:
                return match

        if classroom is not None:
            match = cls.objects.filter(
                academic_year=academic_year,
                classroom=classroom,
                term__isnull=True,
            ).first()
            if match:
                return match

        if term is not None:
            match = cls.objects.filter(
                academic_year=academic_year,
                classroom__isnull=True,
                term=term,
            ).first()
            if match:
                return match

        match = cls.objects.filter(
            academic_year=academic_year,
            classroom__isnull=True,
            term__isnull=True,
        ).first()
        if match:
            return match

        return cls.objects.create(
            academic_year=academic_year,
            classroom=classroom if classroom is not None else None,
            term=term if term is not None else None,
        )


def _assessment_weights_scale_bands_pre_save(sender, instance, **kwargs):  # noqa: ARG001
    _apply_scale_consistent_bands(instance)


models.signals.pre_save.connect(
    _assessment_weights_scale_bands_pre_save,
    sender=AssessmentWeights,
    dispatch_uid="assessment_weights_scale_consistent_bands",
)


class GradingScale(models.Model):
    """
    Plan III: Polymorphic grading scale tied to curriculum/school.
    Schools can define custom scales or use built-in (numeric_0_20, gpa_4_0, etc.).
    AssessmentWeights can reference this via grading_scale_fk for consistent GradeConverter use.
    """

    class ScaleType(models.TextChoices):
        NUMERIC_0_20 = "numeric_0_20", "Numeric 0–20"
        LETTER_A_E = "letter_a_e", "Letters A–E"
        GPA_4_0 = "gpa_4_0", "GPA 4.0"
        PERCENTAGE = "percentage", "Percentage 0–100"
        NUMERIC_1_5 = "numeric_1_5", "Numeric 1–5 (Post-Soviet)"
        WAEC_LETTER = "waec_letter", "WAEC letter bands (A1–F9)"
        PASS_FAIL = "pass_fail", "Pass / Fail"
        QUALITATIVE_PD = "qualitative_pd", "Qualitative descriptors"
        STANDARD_SCORE_T = "standard_score_t", "T-score (East Asia)"
        # International curriculum scales — match the AssessmentWeights.grading_scale
        # choices, the registry REQUIRED_CODES, and the EXTENDED_GRADE_BANDS families,
        # so a per-school GradingScale row can durably select any of them.
        UK_GCSE_9_1 = "uk_gcse_9_1", "UK GCSE 9–1"
        IB_1_7 = "ib_1_7", "IB 1–7"
        GERMAN_1_6 = "german_1_6", "German 1–6"
        CBSE_10 = "cbse_10", "CBSE 10-point (A1–E2)"
        FRENCH_0_20 = "french_0_20", "French 0–20"
        US_LETTER = "us_letter", "US letter A–F"

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="grading_scales",
        help_text="Null = global template (e.g. Apply a Template at signup).",
    )
    code = models.SlugField(
        max_length=64,
        blank=True,
        help_text="Stable key within the tenant (optional). Used by integrations and templates.",
    )
    region = models.ForeignKey(
        "siteconfig.RegionConfig",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evals_grading_scales",
        help_text="Optional linkage to a regional template.",
    )
    name = models.CharField(max_length=80, help_text="e.g. Cameroon 0-20, GPA 4.0")
    scale_type = models.CharField(
        max_length=50, choices=ScaleType.choices, default=ScaleType.NUMERIC_0_20
    )
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Optional: min, max, grade_thresholds (A_min, B_min, ...) for letter conversion.",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="When true, use as default for this school when no AssessmentWeights override.",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Inactive scales are ignored when resolving the effective scale.",
    )

    class Meta:
        ordering = ["school_id", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "name"],
                name="evals_gradingscale_school_name_uniq",
            ),
            models.UniqueConstraint(
                fields=["school", "code"],
                condition=~Q(code=""),
                name="evals_gradingscale_school_code_nonempty_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_scale_type_display()})"


class GradingScaleBand(models.Model):
    """
    Non-overlapping score bands for a tenant grading scale (North Star SLICE 2).
    Normalized bounds align with Rosetta 0.0–1.0 for cross-system reporting.
    """

    grading_scale = models.ForeignKey(
        GradingScale,
        on_delete=models.CASCADE,
        related_name="bands",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    min_score = models.DecimalField(max_digits=12, decimal_places=4)
    max_score = models.DecimalField(max_digits=12, decimal_places=4)
    label = models.CharField(max_length=120)
    band_weight = models.PositiveSmallIntegerField(
        default=100,
        help_text="Relative weight for aggregates when applicable.",
    )
    grade_point = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Optional GPA / points value for this band.",
    )
    normalized_min = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        help_text="Inclusive lower bound on the 0.0–1.0 Rosetta axis.",
    )
    normalized_max = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        help_text="Inclusive upper bound on the 0.0–1.0 Rosetta axis.",
    )

    class Meta:
        ordering = ["grading_scale_id", "sort_order", "min_score"]

    def __str__(self):
        return f"{self.grading_scale}: {self.label}"

    def clean(self):
        super().clean()
        mn = self.min_score
        mx = self.max_score
        if mn is not None and mx is not None and mn > mx:
            raise ValidationError({"min_score": "min_score cannot exceed max_score."})

        for fld in ("normalized_min", "normalized_max"):
            val = getattr(self, fld)
            if val is not None:
                if val < 0 or val > 1:
                    raise ValidationError(
                        {fld: "Normalized bounds must be between 0 and 1 inclusive."}
                    )

        if (
            self.normalized_min is not None
            and self.normalized_max is not None
            and self.normalized_min > self.normalized_max
        ):
            raise ValidationError(
                {"normalized_min": "normalized_min cannot exceed normalized_max."}
            )

        siblings = GradingScaleBand.objects.filter(
            grading_scale_id=self.grading_scale_id
        )
        if self.pk:
            siblings = siblings.exclude(pk=self.pk)
        for other in siblings:
            if self._intervals_overlap(
                self.min_score,
                self.max_score,
                other.min_score,
                other.max_score,
            ):
                raise ValidationError(
                    "Bands cannot overlap on raw scores within the same grading scale."
                )

    @staticmethod
    def _intervals_overlap(a_min, a_max, b_min, b_max):
        if None in (a_min, a_max, b_min, b_max):
            return False
        # True if the intersection has positive width (shared boundary at one point is allowed).
        return max(a_min, b_min) < min(a_max, b_max)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class TeacherAssignment(models.Model):
    """
    Teacher is allowed to enter marks for a given SubjectAssignment in an AcademicYear.
    """

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="teacher_assignments",
    )
    teacher = models.ForeignKey(
        TeacherProfile, on_delete=models.CASCADE, related_name="assignments"
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="teacher_assignments"
    )
    subject_assignment = models.ForeignKey(
        SubjectAssignment, on_delete=models.CASCADE, related_name="teacher_assignments"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("teacher", "academic_year", "subject_assignment")

    def clean(self):
        # Enforce year consistency between assignment and subject_assignment
        if (
            self.subject_assignment
            and self.academic_year
            and self.subject_assignment.academic_year_id != self.academic_year_id
        ):
            raise ValidationError(
                "SubjectAssignment academic year must match TeacherAssignment academic year."
            )

    def __str__(self):
        return f"{self.teacher} -> {self.subject_assignment}"


# Exception tuples for Evaluation.save(): computing total_score / normalized
# value can fail on bad arithmetic, missing relations, or type coercion. Catch
# narrowly and fall back to None rather than crashing the save. ArithmeticError
# covers ZeroDivisionError + decimal.InvalidOperation without extra imports.
_EVALS_MODEL_SAVE_FINAL_SCORE_ERRORS = (TypeError, ValueError, AttributeError, ArithmeticError)
_EVALS_MODEL_SAVE_NORMALIZED_ERRORS = (TypeError, ValueError, AttributeError, ArithmeticError)


class Evaluation(models.Model):
    """
    One row per student per subject_assignment per term.
    Phase 4: Critical model for audit logging (grade changes).
    """

    # Phase 4: Enable audit logging for this critical model
    audit_enabled = True

    school = models.ForeignKey(
        "schools.School",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="evaluations",
    )
    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.PROTECT, related_name="evaluations"
    )
    term = models.ForeignKey(Term, on_delete=models.PROTECT, related_name="evaluations")
    subject_assignment = models.ForeignKey(
        SubjectAssignment, on_delete=models.PROTECT, related_name="evaluations"
    )
    student = models.ForeignKey(
        StudentProfile, on_delete=models.PROTECT, related_name="evaluations"
    )
    teacher = models.ForeignKey(
        TeacherProfile, on_delete=models.PROTECT, related_name="evaluations"
    )

    # Backward compatible fields (old UI). New UI should use seq1/seq2.
    test1 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    test2 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Pass 8.D (2026-05-11): per-component scores. The hard MaxValueValidator(20)
    # was removed — schools now declare their max via the GradingScale they bind
    # to their region (US 0-100, UK 0-100, Cameroon 0-20, IB 0-7, etc.).
    # Forms / views enforce the tenant-resolved max; the model itself only
    # enforces the lower bound and the column's max_digits=5,decimal_places=2.
    seq1_score = models.DecimalField(
        "Seq 1",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    seq2_score = models.DecimalField(
        "Seq 2",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    exam_score = models.DecimalField(
        "Exam",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    mock_score = models.DecimalField(
        "Mock",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    practical_score = models.DecimalField(
        "Practical",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    internship_score = models.DecimalField(
        "Industrial attachment / Internship",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Industrial attachment (Paper 3) or internship mark; may sync to sequence.",
    )
    remarks = models.CharField(max_length=255, blank=True)

    # NEW: Grade conversion & practical assessment
    letter_grade = models.CharField(
        max_length=1,
        choices=[
            ("A", "A"),
            ("B", "B"),
            ("C", "C"),
            ("D", "D"),
            ("E", "E"),
            ("", "Not Graded"),
        ],
        blank=True,
        default="",
    )
    clock_hours = models.PositiveIntegerField(default=0)
    practical_status = models.CharField(
        max_length=20,
        choices=[
            ("not_started", "Not Started"),
            ("in_progress", "In Progress"),
            ("completed", "Completed"),
        ],
        default="not_started",
    )
    assessment_date = models.DateField(null=True, blank=True)
    validation_flags = models.JSONField(default=dict, blank=True)
    last_validated_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Final computed score stored for aggregation and reporting (kept in DB for performance)
    final_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    # Normalized score 0.0–1.0 for cross-tenant / cross-system reporting (Rosetta Stone)
    normalized_value = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Score normalized to 0.0–1.0 for cross-system grade conversion and reporting.",
    )

    # Audit logging fields for data integrity
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluations_created",
        help_text="User who created this evaluation",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="evaluations_updated",
        help_text="User who last updated this evaluation",
    )
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Soft delete timestamp - preserves evaluation history",
    )
    # Client-generated id for a mark entered offline on an edge box; lets the operator
    # upsert it by (school, client_offline_id) on sync without pk collisions. The row
    # itself is DOWN-ONLY (grade_entry is a protected policy) — a box push never
    # silently overwrites the cloud's mark; it raises a Sync Center conflict.
    client_offline_id = models.CharField(max_length=128, blank=True, db_index=True)

    @property
    def total_score(self) -> float:
        """Single score used for ranking/statistics.

        Uses AssessmentWeights + tenant GradingScale formula when configured;
        otherwise weighted mean of components (legacy path).
        """
        from apps.evals.grade_computation import compute_evaluation_total_score

        return compute_evaluation_total_score(self)

    @property
    def is_complete_for_ranking(self) -> bool:
        """True when all required (weighted) components have scores."""
        weights = AssessmentWeights.get_for(
            academic_year=self.academic_year,
            classroom=self.subject_assignment.classroom
            if self.subject_assignment_id
            else None,
            term=self.term,
        )
        s1 = self.seq1_score if self.seq1_score is not None else self.test1
        s2 = self.seq2_score if self.seq2_score is not None else self.test2
        req = []
        if weights.seq1_weight > 0:
            req.append(s1)
        if weights.seq2_weight > 0:
            req.append(s2)
        if weights.exam_weight > 0:
            req.append(self.exam_score)
        if weights.mock_weight > 0:
            req.append(self.mock_score)
        if weights.practical_weight > 0:
            req.append(self.practical_score)
        return all(v is not None for v in req)

    class Meta:
        unique_together = ("academic_year", "term", "subject_assignment", "student")
        constraints = [
            models.UniqueConstraint(
                fields=["school", "client_offline_id"],
                condition=~models.Q(client_offline_id=""),
                name="uniq_evaluation_school_offline_id",
            ),
        ]

    def _resolve_grading_school(self):
        """The school whose grading scale bounds this row's scores.

        ``resolve_school_score_scale`` now REFUSES to answer for a missing school
        (it used to return a neutral 100, so every link that failed to find a
        school silently WIDENED the accepted range: a /20 Cameroon school then
        accepted a mark of 25). Resolving the school here is therefore what keeps
        a legitimate row saveable, not merely what keeps it bounded. The row's own ``school`` FK is
        nullable and frequently unset (schema isolation makes it redundant, so
        seeders and bulk writers omit it), and ``SubjectAssignment.school`` is
        nullable for the same reason — so both original links miss together.
        Walk the rest of the graph, then fall back to the tenant the connection
        is scoped to, before conceding None.
        """
        school = getattr(self, "school", None)
        if school is not None:
            return school
        for owner_attr, fk_id in (
            ("subject_assignment", self.subject_assignment_id),
            ("student", self.student_id),
            ("academic_year", self.academic_year_id),
            ("term", self.term_id),
        ):
            if not fk_id:
                continue
            owner = getattr(self, owner_attr, None)
            school = getattr(owner, "school", None)
            if school is not None:
                return school
        # Classroom hangs off the assignment, not off this row.
        sa = getattr(self, "subject_assignment", None) if self.subject_assignment_id else None
        school = getattr(getattr(sa, "classroom", None), "school", None)
        if school is not None:
            return school
        from apps.schools.rls_context import resolve_connection_school

        return resolve_connection_school()

    def clean(self):
        # Score upper-bound = the school's OPERATIONAL grade scale
        # (AssessmentWeights.score_scale via resolve_school_score_scale), NOT the
        # locale-derived max_score_for_school which lags the per-school seeded scale
        # (it reports 100 for a /20 francophone school) and would accept out-of-range
        # scores. Consistent with OCR/EWS validation and how grades are actually scored.
        from apps.evals.grading_provisioning import (
            UNRESOLVED_SCALE_FALLBACK_MAX,
            UnresolvedScoreScale,
            resolve_school_score_scale,
        )

        school = self._resolve_grading_school()
        # No default= on purpose: this is the upper bound, so it must FAIL CLOSED.
        # The resolver used to hand back a neutral 100 for an unresolvable school,
        # which turned a broken link into a silently WIDER accepted range — that is
        # how a /20 Cameroon school accepted a mark of 25. When the school cannot be
        # resolved at all we clamp to the NARROWEST bound instead, so the failure
        # mode over-rejects (loud) rather than over-admits (silent). Same fallback
        # the OCR validator and the marks-grid `max=` attribute already use.
        try:
            max_score = resolve_school_score_scale(school)
        except UnresolvedScoreScale:
            max_score = UNRESOLVED_SCALE_FALLBACK_MAX

        score_fields = {
            "seq1_score": self.seq1_score,
            "seq2_score": self.seq2_score,
            "exam_score": self.exam_score,
            "mock_score": self.mock_score,
            "practical_score": self.practical_score,
        }

        for field_name, score in score_fields.items():
            if score is not None:
                if score < 0:
                    raise ValidationError(
                        {field_name: f"{field_name} cannot be negative"}
                    )
                if score > max_score:
                    raise ValidationError(
                        {
                            field_name: (
                                f"{field_name} cannot exceed {max_score} "
                                f"for this school's grading scale"
                            )
                        }
                    )

        # At least one score must be entered
        scores = [s for s in score_fields.values() if s is not None]
        if not scores and not self.test1 and not self.test2:
            raise ValidationError("At least one score must be entered")

        # enforce year/term match
        if (
            self.term
            and self.academic_year
            and self.term.academic_year_id != self.academic_year_id
        ):
            raise ValidationError(
                "Term academic year must match Evaluation academic year."
            )
        # enforce subject assignment matches year/term
        if (
            self.subject_assignment
            and self.academic_year
            and self.subject_assignment.academic_year_id != self.academic_year_id
        ):
            raise ValidationError("SubjectAssignment year must match Evaluation year.")
        if (
            self.subject_assignment
            and self.term
            and self.subject_assignment.term_id != self.term_id
        ):
            raise ValidationError("SubjectAssignment term must match Evaluation term.")
        # enforce student in same year/class/specialty as subject assignment
        if self.subject_assignment and self.student:
            sa = self.subject_assignment
            if self.student.academic_year_id != sa.academic_year_id:
                raise ValidationError("Student year must match SubjectAssignment year.")
            if (
                self.student.classroom_id != sa.classroom_id
                or self.student.specialty_id != sa.specialty_id
            ):
                raise ValidationError(
                    "Student class/specialty must match SubjectAssignment class/specialty."
                )

    def save(self, *args, **kwargs):
        """Call full_clean() before saving to validate scores and persist final_score and normalized_value."""
        self.full_clean()
        # Persist final_score for efficient aggregation/reporting
        try:
            self.final_score = self.total_score
        except _EVALS_MODEL_SAVE_FINAL_SCORE_ERRORS:
            self.final_score = None
        # Persist normalized_value (0.0–1.0) for cross-tenant/cross-system (Rosetta Stone)
        try:
            from apps.evals.grading import score_to_normalized

            school = getattr(self, "school", None)
            if self.final_score is not None:
                self.normalized_value = score_to_normalized(
                    float(self.final_score), school
                )
            else:
                self.normalized_value = None
        except _EVALS_MODEL_SAVE_NORMALIZED_ERRORS:
            self.normalized_value = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} | {self.subject_assignment.subject} | {self.term}"


def _evaluation_evidence_upload_to(instance, filename):
    """Tenant-scoped path for EvaluationEvidence.file (Section 25.3). School from evaluation."""
    ev = getattr(instance, "evaluation", None)
    school_id = getattr(ev, "school_id", None) if ev else None
    if school_id is None:
        return f"tenant_uploads/evals/evidence/{filename}"
    return f"tenants/{school_id}/evals/evidence/{filename}"


class EvaluationEvidence(models.Model):
    class MediaType(models.TextChoices):
        PHOTO = "PHOTO", "Photo"
        VIDEO = "VIDEO", "Video"
        DOCUMENT = "DOCUMENT", "Document"

    evaluation = models.ForeignKey(
        Evaluation, on_delete=models.CASCADE, related_name="evidence"
    )
    media_type = models.CharField(
        max_length=20, choices=MediaType.choices, default=MediaType.PHOTO
    )
    file = models.FileField(
        upload_to=_evaluation_evidence_upload_to,
        validators=[validate_evidence_file, validate_file_size_20mb],
    )
    caption = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.evaluation} - {self.get_media_type_display()}"


# ========== GRADE AUDIT TRAIL ==========


class GradeAudit(models.Model):
    """Immutable audit trail for all grade changes.
    Phase 4: Enable audit logging to track audit record creation.
    """

    # Phase 4: Enable audit logging for this model
    audit_enabled = True

    CHANGE_TYPE_CHOICES = [
        ("create", "Grade Created"),
        ("update", "Grade Updated"),
        ("delete", "Grade Deleted"),
        ("rollback", "Grade Rolled Back"),
        ("import", "Imported from CSV"),
        ("offline_sync", "Synced Offline Entry"),
    ]

    evaluation = models.ForeignKey(
        Evaluation, on_delete=models.PROTECT, related_name="audit_trail"
    )
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    changed_by = models.ForeignKey(
        User, on_delete=models.PROTECT, null=True, blank=True
    )
    change_type = models.CharField(max_length=20, choices=CHANGE_TYPE_CHOICES)

    # Before/after snapshots
    seq1_before = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    seq1_after = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    seq2_before = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    seq2_after = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    exam_before = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    exam_after = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    mock_before = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    mock_after = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    practical_before = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    practical_after = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    remarks_before = models.TextField(null=True, blank=True)
    remarks_after = models.TextField(null=True, blank=True)

    # Validation & conflict
    validation_errors = models.JSONField(default=list, blank=True)
    offline_conflict_resolved = models.BooleanField(default=False)
    conflict_resolution_note = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ["-changed_at"]
        indexes = [
            models.Index(fields=["evaluation", "-changed_at"]),
            models.Index(fields=["changed_by", "-changed_at"]),
            models.Index(fields=["change_type", "-changed_at"]),
        ]

    def __str__(self):
        return f"{self.get_change_type_display()} - {self.evaluation}"


class GradeApprovalRequest(models.Model):
    """Tracks manual grade submissions that need staff approval."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending Review"
        UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
        REVISION_REQUESTED = "REVISION_REQUESTED", "Revision Requested"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.PROTECT,
        related_name="grade_approval_requests",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name="grade_approval_requests",
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.PROTECT,
        related_name="grade_approval_requests",
    )
    subject_assignment = models.ForeignKey(
        SubjectAssignment,
        on_delete=models.PROTECT,
        related_name="grade_approval_requests",
    )
    entries = models.JSONField(default=list, blank=True)
    summary = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=30, choices=Status.choices, default=Status.PENDING
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="grade_approval_requests_created",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="grade_approval_requests_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewer_notes = models.TextField(blank=True)

    # Bypass / escalation (when an approver is unavailable)
    bypassed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="grade_approval_requests_bypassed",
        help_text="User who bypassed the normal approval chain.",
    )
    bypassed_at = models.DateTimeField(null=True, blank=True)
    bypass_reason = models.TextField(blank=True)
    bypassed_from_status = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self):
        subject = getattr(self.subject_assignment, "subject", None)
        student_count = self.summary.get("total_students", 0)
        return f"{subject or 'Subject'} ({student_count} students) · {self.get_status_display()}"

    def mark_reviewed(self, reviewer: User, status: str, notes: Optional[str] = None):
        self.status = status
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        if notes is not None:
            self.reviewer_notes = notes
        self.save(
            update_fields=["status", "reviewed_by", "reviewed_at", "reviewer_notes"]
        )

    def mark_bypassed(
        self,
        *,
        by_user: User,
        new_status: str,
        reason: str,
        notes: Optional[str] = None,
    ):
        """Bypass the normal chain and record a final decision with audit metadata."""
        self.bypassed_by = by_user
        self.bypassed_at = timezone.now()
        self.bypass_reason = reason or ""
        self.bypassed_from_status = self.status
        # also set the decision fields as the effective review action
        self.status = new_status
        self.reviewed_by = by_user
        self.reviewed_at = self.bypassed_at
        if notes is not None:
            self.reviewer_notes = notes
        self.save(
            update_fields=[
                "bypassed_by",
                "bypassed_at",
                "bypass_reason",
                "bypassed_from_status",
                "status",
                "reviewed_by",
                "reviewed_at",
                "reviewer_notes",
            ]
        )

    @property
    def is_overdue(self):
        # Deadline functionality removed - always return False
        return False

    @property
    def is_bypassed(self) -> bool:
        return bool(self.bypassed_at or self.bypassed_by_id)


# ========== OFFLINE SYNC QUEUE ==========


class OfflineMarkEntry(models.Model):
    """Queue for marks entered offline, synced when connected."""

    STATUS_CHOICES = [
        ("pending", "Pending Sync"),
        ("synced", "Successfully Synced"),
        ("conflict", "Sync Conflict"),
        ("rejected", "Rejected"),
    ]

    teacher = models.ForeignKey(TeacherProfile, on_delete=models.PROTECT)
    subject_assignment = models.ForeignKey(SubjectAssignment, on_delete=models.PROTECT)
    student = models.ForeignKey(StudentProfile, on_delete=models.PROTECT)
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.PROTECT)
    term = models.ForeignKey(Term, on_delete=models.PROTECT)

    # Grade data
    seq1_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    seq2_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    exam_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    mock_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    practical_score = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    remarks = models.TextField(blank=True)

    # Sync metadata
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    created_offline_at = models.DateTimeField()
    synced_at = models.DateTimeField(null=True, blank=True)
    synced_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )

    # Conflict resolution
    conflict_with_evaluation = models.ForeignKey(
        Evaluation, on_delete=models.SET_NULL, null=True, blank=True
    )
    teacher_conflict_choice = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["status", "created_offline_at"]
        indexes = [
            models.Index(fields=["teacher", "status"]),
            models.Index(fields=["created_offline_at"]),
        ]

    def __str__(self):
        return f"Offline: {self.student.student_code} - {self.subject_assignment.subject.name}"


class MockExamSetting(models.Model):
    """Configuration for mock exam score blending (Phase 1.2.3).

    Allows schools to blend mock exam scores with final exam scores for advanced forms
    (FORM 5, FORM 7, UPPER 6, etc.). One setting per classroom/term combination.

    Default: 70% final exam + 30% mock exam score (disabled by default).
    """

    academic_year = models.ForeignKey(
        AcademicYear, on_delete=models.CASCADE, related_name="mock_exam_settings"
    )
    classroom = models.ForeignKey(
        "academics.Classroom",
        on_delete=models.CASCADE,
        related_name="mock_exam_settings",
    )
    term = models.ForeignKey(
        Term, on_delete=models.CASCADE, related_name="mock_exam_settings"
    )

    # Weight configuration (must sum to 100% if is_active=True)
    final_weight = models.PositiveSmallIntegerField(
        default=70,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Weight for final exam score (0-100%)",
    )
    mock_weight = models.PositiveSmallIntegerField(
        default=30,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Weight for mock exam score (0-100%)",
    )
    is_active = models.BooleanField(
        default=False, help_text="Enable score blending for this classroom/term"
    )

    # Audit timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("academic_year", "classroom", "term")
        indexes = [
            models.Index(fields=["academic_year", "classroom", "term"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"Mock Settings: {self.classroom.name} ({self.term.name})"

    def clean(self):
        """Validate that weights sum to 100% when active."""
        if self.is_active:
            total = self.final_weight + self.mock_weight
            if total != 100:
                raise ValidationError(
                    f"When active, weights must sum to 100%. Got: {total}% "
                    f"({self.final_weight}% final + {self.mock_weight}% mock)"
                )

    def save(self, *args, **kwargs):
        """Validate before saving."""
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def get_for(cls, academic_year, classroom, term):
        """Get or create with defaults (disabled by default)."""
        setting, _ = cls.objects.get_or_create(
            academic_year=academic_year,
            classroom=classroom,
            term=term,
            defaults={
                "is_active": False,
                "final_weight": 70,
                "mock_weight": 30,
            },
        )
        return setting
