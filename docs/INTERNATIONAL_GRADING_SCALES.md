# International grading scales — registry ↔ operational bridge (SOT)

This is the reference for how RunMyCampus advertises **15 world grading scales**
and proves that every advertised scale is actually *computable* — i.e. that "the
catalog offers N scales" and "teachers can grade on N scales" are provably the
same set, and that a raw score maps to the correct displayed band per scale
(including inverted scales like German 1–6).

> **TL;DR** — Three layers must agree 1:1: the `GradeScaleRegistry` advertised
> codes (`REQUIRED_CODES`, 15), the operational `AssessmentWeights` scale types
> that compute them, and the `EXTENDED_GRADE_BANDS` that render their rich labels.
> `REGISTRY_SCALE_TYPE_MAP` is the explicit bridge between the first two; a
> coverage gate + keystone test fail on any drift. `resolve_extended_band_label`
> turns a raw score into the scale-native band, with a direction flag for German.

---

## 1. The bridge: `REGISTRY_SCALE_TYPE_MAP`

[`apps/evals/grading.py`](../apps/evals/grading.py) `REGISTRY_SCALE_TYPE_MAP`
(`:220`) maps each advertised registry code → the operational `AssessmentWeights`
scale type that computes it. It is documented in-file as "THE bridge between the
two grading systems" and "must stay 1:1 with `REQUIRED_CODES`" (`grading.py:214`).

The 15 entries:

| Registry code | Operational scale_type |
|---------------|------------------------|
| `0-20` | `numeric_0_20` |
| `0-100` | `percentage` |
| `GPA_4` | `gpa_4_0` |
| `LETTER` | `letter_a_e` |
| `PASS_FAIL` | `pass_fail` |
| `NUMERIC_1_5` | `numeric_1_5` |
| `WAEC_LETTER` | `waec_letter` |
| `STANDARD_SCORE_T` | `standard_score_t` |
| `QUALITATIVE_PD` | `qualitative_pd` |
| `UK_GCSE_9_1` | `uk_gcse_9_1` |
| `IB_1_7` | `ib_1_7` |
| `GERMAN_1_6` | `german_1_6` |
| `CBSE_10` | `cbse_10` |
| `FRENCH_0_20` | `french_0_20` |
| `US_LETTER` | `us_letter` |

`REQUIRED_CODES` (the advertised set) lives in
`scripts/verify_grading_scale_registry_coverage.py:15` and lists exactly these 15
codes. The operational scale types are the `GradingScale.ScaleType` /
`AssessmentWeights.grading_scale` choices (`apps/evals/models.py:388`–`:406`).

> History (verified in-file comment, `grading.py:230`): the registry/seed already
> advertised all 15, but the operational bridge had drifted behind at 9, so 6
> international scales were registry-known yet not provably computable. The 6 were
> wired in to close the bridge.

## 2. Score → band: `resolve_extended_band_label`

`EXTENDED_GRADE_BANDS` (`apps/evals/models.py:58`) holds rich band labels for the
scales whose grade representation does NOT fit the ordinary 5-band A–E numeric
model. `resolve_extended_band_label(scale, score)` (`apps/evals/models.py:138`)
turns a raw score into that scale's native label, or returns `None` for ordinary
5-band scales (callers then fall back to the coarse A–E letter). It never raises.

Covered families and how a score maps:

| Scale | `score_scale` | Bands (best → worst) | Direction |
|-------|--------------|----------------------|-----------|
| `waec_letter` | 100 | A1 ≥75, B2 ≥70, B3 ≥65, C4 ≥60, C5 ≥55, C6 ≥50, D7 ≥45, E8 ≥40, F9 ≥0 (`models.py:59`) | descending (higher = better) |
| `pass_fail` | 100 | Pass ≥50, Fail ≥0 (`:67`) | descending |
| `qualitative_pd` | 100 | Exceeding ≥85, Meeting ≥70, Approaching ≥50, Beginning ≥0 (`:72`) | descending |
| `uk_gcse_9_1` | 9 | 9…1, each whole grade its own band (`:85`) | descending |
| `ib_1_7` | 7 | 7…1, each whole grade its own band (`:95`) | descending |
| `cbse_10` | 10 | A1=10, A2=9, B1=8, B2=7, C1=6, C2=5, D=4, E1≥2, E2≥0 (`:106`) | descending |
| `german_1_6` | 6 | 1 ≤1.49, 2 ≤2.49, 3 ≤3.49, 4 ≤4.49, 5 ≤5.49, 6 ≤6.0 (`:119`) | **ascending (lower = better)** |

### The German 1–6 inversion (the one special case)

German 1–6 is the only family where a **lower** score is a **better** grade (1 =
*sehr gut* best, 6 = *ungenügend* worst). It carries `"direction": "ascending"`
(`models.py:122`). In `resolve_extended_band_label`:

- ascending scales list bands best→worst by **ceiling** (`max_score`) and the
  function returns the first band whose ceiling the value is within (`value <=
  max_score`), capping at the worst band (`models.py:165`–`:173`);
- all other (descending) scales list bands best→worst by **floor** (`min_score`)
  and return the first band the value clears (`value >= min_score`), flooring at
  the lowest band (`models.py:174`–`:178`).

The boundaries (`1: ≤1.49 … 6: ≤6.0`, pass at 4) are the standard rounding model
for German averages. Cross-scale numeric conversion is NOT meaningful for German,
so its band label is always authoritative — `grading.py:204` notes the `0-10`
entry in the display map is a structural home only (every scale must map), not a
conversion path.

`format_grade_band(scale_type, score)` (`grading.py:281`) is the helper to call
anywhere a grade is shown: it returns the rich band for the extended families and
the ordinary A–E letter for the numeric scales, and never raises.

## 3. T-score is cohort-relative, not a fixed band

`standard_score_t` is registered but is **not** a fixed-band family. The T-score
(Japanese *hensachi*) `T = 50 + 10·(x − mean)/sd` is computed over a whole cohort
by `cohort_t_scores(raw_scores)` (`grading.py:302`) — a single mark has no T-score
in isolation. With < 2 graded marks or zero spread, every T is the mean 50.0. The
coarse bands in `GRADING_SCALE_BANDS` for `standard_score_t` (`models.py:39`) only
drive `score_scale` + the single-score letter fallback.

## 4. How a tenant adopts a scale

- Per school: create a `GradingScale` row with the chosen `ScaleType`
  (`apps/evals/models.py:381`), or set `AssessmentWeights.grading_scale` to the
  operational scale type.
- The school's active scale id for display/conversion is resolved by
  `get_scale_for_school(school)` (`grading.py:325`), which reads tenant config via
  `get_grading_schema_for_school` and normalizes it with `normalize_scale_id`
  (`grading.py:260`). `REGION_SCALE_ALIASES` (`grading.py:243`) tolerates many
  token spellings (e.g. `uk_honours`/`uk-honors`, `ib`/`ib_0_7`).
- Cross-scale conversion (when both systems are in use) goes through
  `convert_score(score, from_scale, to_scale)` (`grading.py:128`), which
  normalizes to 0–1 and rescales; `GRADING_SCALES` (`grading.py:13`) holds the
  min/max + display lambda per display-scale id.

## 5. What is proven

[`apps/evals/tests/test_grading_scale_world_coverage.py`](../apps/evals/tests/test_grading_scale_world_coverage.py)
— the keystone:

| Test | Proves |
|------|--------|
| `test_every_registry_code_is_operational` (`:77`) | `REGISTRY_SCALE_TYPE_MAP` keys == the coverage gate's `REQUIRED_CODES` (no drift) |
| `test_all_world_scales_operationally_resolvable` (`:94`) | all 15 codes map 1:1 to distinct operational scale types |
| `CohortTScoreTests` (`:40`) | the T-score formula, midpoint=50, zero-spread/too-small cohort, None preservation |
| `StandardScoreTRegistrationTests` (`:59`) | T-score is registered but not a fixed-band family; single-score display falls back to coarse letter |

Related:
- [`apps/evals/tests/test_grading_scale_band_families.py`](../apps/evals/tests/test_grading_scale_band_families.py) — WAEC / Pass-Fail / qualitative band resolution.
- [`apps/evals/tests/test_grading_scale_international_curriculum.py`](../apps/evals/tests/test_grading_scale_international_curriculum.py) — UK GCSE / IB / German / CBSE / French / US.

The CI gate `scripts/verify_grading_scale_registry_coverage.py` (REQUIRED_GATES
member; see CLAUDE.md) seeds the registry and fails if any of the 15
`REQUIRED_CODES` is missing — durability backed by `GRADE_SCALE_SEED_DEFAULTS` +
migration 0008.

## 6. Honest scope / limitations

- This documents the *operational ↔ display bridge* and band resolution. Whether a
  given subject/term *uses* a scale is per-school config (`GradingScale` /
  `AssessmentWeights`), not enforced here.
- German 1–6 cross-conversion is intentionally NOT supported (the band label is
  authoritative); its `0-10` display-map entry is structural, not a conversion
  path (`grading.py:204`).
- The coarse `GRADING_SCALE_BANDS` A–E tiers for the extended families exist only
  to keep `score_scale` + the legacy single-char `Evaluation.letter_grade` working
  (`models.py:30`); the *shown* grade comes from `EXTENDED_GRADE_BANDS`.
