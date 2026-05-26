"""Wave R-B (v3.96.0 — 2026-05-26) — Admission application kernel.

Lifts the admissions funnel from "Applicant row exists" to a guided 5-stage
application flow with document checklist, stage transitions, and Applicant →
StudentProfile enrollment. No new model: payload extensions live in the
existing ``Applicant.extra_data`` JSONField so this wave ships ZERO new
migrations.
"""
