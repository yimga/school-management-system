# apps/evals

> Marks entry, grade computation, the per-tenant grading scale, and the ranking
> and audit surfaces that read the result.

**Tenancy:** TENANT (own Postgres schema under django-tenants)
**Scale:** 10 models · 38 migrations · 31 test modules · ~19.5k LOC

## What this app owns

Evals owns the number a teacher types and everything that number becomes. It
owns the marks grid, the weighting configuration, the bulk import and OCR paths,
the offline mark queue, the approval workflow for manual submissions, the
immutable grade audit trail, and class/school ranking.

Two decisions shape the whole app.

**First: the grading scale is data, not a constant.** A school is not assumed to
grade out of 100. `GradingScale` is polymorphic across sixteen scale types —
French 0–20, GPA 4.0, WAEC A1–F9, UK GCSE 9–1, IB 1–7, German 1–6, CBSE, the
post-Soviet 1–5, T-scores, pass/fail, qualitative descriptors — and
`GradingScaleBand` gives a tenant explicit, non-overlapping bands on top. Every
band also declares `normalized_min` / `normalized_max` on a shared 0.0–1.0 axis,
which is what makes `rosetta_stone` able to convert a mark between systems (a
French 16/20 becomes a US 3.2 / B+) for student mobility.

**Second: `Evaluation.final_score` is a denormalized column, and only
`Evaluation.save()` may write it.** `save()` computes `final_score` from the
raw component scores and derives `normalized_value` from it via the school's
scale. Rankings (`Avg("final_score")`), the degree-audit credit check, the EWS
grade-drop detector, and frozen transcripts all read the *stored* column. That
makes any write path that bypasses `save()` a silent data-integrity bug, which
is exactly what happened once and is now a named regression test.

## Key models

All ten. This app is deliberately narrow at the schema level.

| Model | Table | Purpose |
| --- | --- | --- |
| `Evaluation` | `evals_evaluation` | One row per student per subject_assignment per term. Holds the raw components plus the denormalized `final_score` / `normalized_value` |
| `AssessmentWeights` | `evals_assessmentweights` | Which components count and how much — decides which fields the marks grid even requires |
| `GradingScale` | `evals_gradingscale` | Polymorphic per-school (or global-template) scale. `school=None` means a template |
| `GradingScaleBand` | `evals_gradingscaleband` | Non-overlapping bands with labels, optional grade points, and Rosetta 0.0–1.0 bounds |
| `TeacherAssignment` | `evals_teacherassignment` | Authorization row: this teacher may enter marks for this SubjectAssignment in this year |
| `GradeAudit` | `evals_gradeaudit` | Immutable before/after trail for every grade change (create/update/delete/rollback/import/offline_sync) |
| `GradeApprovalRequest` | `evals_gradeapprovalrequest` | Manual grade submissions awaiting staff approval |
| `OfflineMarkEntry` | `evals_offlinemarkentry` | Marks captured offline; pending → synced / conflict / rejected |
| `EvaluationEvidence` | `evals_evaluationevidence` | Uploaded evidence attached to an evaluation |
| `MockExamSetting` | `evals_mockexamsetting` | Mock-exam score blending configuration |

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `grade_computation`, `grading` | Score conversion / formatting / grade calculation |
| Module | `grading_scale_service` | DB-driven scale + band resolution. Extends, does not replace, the linear converters |
| Module | `rosetta_stone` | Cross-scale conversion through the normalized 0.0–1.0 anchor |
| Module | `grading_formula_engine` | Safe evaluation of tenant-configured formulas — no arbitrary code execution |
| Module | `ranking` | Class/school ranking with tie handling + caching |
| Module | `bulk_gradebook` | Storage-agnostic bulk-entry + rubric kernel; parses percent / points-out-of-N / letter / GPA. Ships zero migrations |
| Module | `offline_sync` | Conflict resolution for `OfflineMarkEntry` |
| Module | `ocr`, `importers` | Scanned and file-based mark intake |
| Celery | `process_bulk_grades` | Async bulk grade application |
| Command | `import_grades`, `grade_import_template`, `mark_completion` | CLI import + template + completion reporting |
| Routes | `teacher_marks_entry`, `bulk_grade_entry`, `grade_approval_list`, `audit_trail`, `class_ranking`, `school_ranking`, `resolve_offline_conflict`, `rosetta_grade_preview_api`, … | Teacher, approver, and drill-down surfaces |

## Before you change this

- **Never write score columns through a queryset `.update()`.** `final_score`
  and `normalized_value` are recomputed only inside `Evaluation.save()`. A bare
  `.update()` writes the raw components and leaves `final_score` frozen at its
  pre-write value *forever* — and every reader of the stored column (rankings,
  degree audit, EWS, frozen transcripts) then reads stale data indefinitely.
  This is not hypothetical: the marks-grid "fill missing scores" bulk action
  shipped exactly that bug. `_apply_fill_missing` (`views.py`) now persists via
  `save()` and the docstring says so; `tests/test_fill_missing_recompute.py`
  keeps a `test_raw_update_leaves_final_score_stale` case that documents the
  desync so nobody re-introduces it. `save()` also reruns validation and fires
  the ranking-cache / audit signals, which `.update()` skips too.
- **`models_enhanced.py` is not live and must not be imported bare.** It is
  currently unimportable (duplicate `EvaluationEvidence` plus a bad
  `CompetencyLevel` reference) and none of its models have migrations, so they
  are never registered — `get_model("evals", "GradeImportJob")` raises
  `LookupError` at runtime, not import time. The live import-job model is
  `analytics.GradeImportJob`. `apps/api/views_v1.py` guards its lazy import and
  degrades those vocational endpoints to HTTP 501 rather than 500; the retired
  `grade_import_job_detail` route in `urls.py` carries a note explaining the
  same trap. Keep any new reference behind a guard. (2026-07-31: the dead
  `OfflineGradeQueue` phantom that lived in this module — referenced nowhere in
  code, no migration, never registered — was deleted as unused scaffolding. The
  real offline-grade rail is `evals.OfflineMarkEntry` plus the SODP/WAL offline
  queues, not this class.)
- **Do not assume 0–100 anywhere.** Resolve the tenant's scale through
  `grading_scale_service` / the canonical band resolver. An out-of-range fill
  must surface as a `ValidationError` to the caller, not be silently written —
  `_apply_fill_missing` propagates it on purpose and lets the view decide how to
  show it.
- **Which components are required is configuration.** `AssessmentWeights`
  decides whether `mock_score` / `practical_score` participate; the field list
  falls back to `seq1_score` / `seq2_score` / `exam_score` only when nothing
  else is weighted. Do not hardcode the component list.
- **`GradeAudit` is an append-only trail** with `on_delete=PROTECT` back to the
  evaluation. It is the evidence record for a grade dispute — do not add an
  update or delete path to it.
- **`TeacherAssignment` is the marks-entry authorization boundary**, unique on
  `(teacher, academic_year, subject_assignment)`. Marks-entry surfaces check it;
  a new entry path must too.
- **`grading_formula_engine` exists so tenant formulas never reach `eval()`.**
  Route any new tenant-configured expression through it.
