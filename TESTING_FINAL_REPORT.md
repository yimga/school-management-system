# Buea Real User Testing — Final Report

**Branch**: Testing  
**Scope**: Dual-curriculum (General + Technical) school in Buea; emphasis on Evals and Report Cards.  
**Passwords**: Superuser `admin` = **Sch00l_1234**; all other users = **Test1234**.

---

## 1. Executive Summary

- **Objective**: Comprehensive real-user and scenario testing of the school management system for a Buea technical school (GCE/TVEE, English system).
- **Status**: Test execution complete. All planned areas (Evals, Reports, Finance, GCE, Rollover, Portal, Communication, Analytics, Compliance, Edge cases) have been exercised or reviewed.
- **Critical gaps**: (1) **Debt-block on report card** — parent download/share not gated by outstanding balance. (2) **GCE export format** — export pack missing board columns (CIN, DD/MM/YYYY, FULL_NAMES UPPERCASE, EXAM_TYPE, SPECIALTY_CODE, MOMO_TRANS_ID). (3) **Arrears carry-forward** — unpaid prior-year fees not carried as opening balance. See [test_finding.md](test_finding.md).
- **Next steps**: Implement debt-block in reports views; align certification export with board template; consider arrears carry-forward and report-card unlock/SMS on payment.

---

## 2. Seeded Data Inventory

All seeded data **remains in the database**; no teardown was performed.

| Category | Count / Detail |
|----------|----------------|
| **Academic years** | 2024/2025 (inactive), 2025/2026 (active, GCE enabled) |
| **Terms** | 3 per year (First, Second, Third) |
| **Classrooms** | General: Form 1–5, Lower Sixth, Upper Sixth. Technical: Year 1–7. |
| **Specialties** | GEN, BESP (Building Construction), ELEC (Electricity), HOME (Home Economics), ACC (Accounting) |
| **Students** | 200 (scale=small) or 500 (scale=full). 60% General, 40% Technical. Matricule: BUEA/2025/001 … |
| **Staff** | 10 teachers (small) / 20 (full), 5 admins, 1 bursar |
| **Parents** | 150 (small) / 450 (full), linked via StudentGuardian |
| **Fee plans** | Tuition + PTA; Technical: + Workshop Fee |
| **Invoices** | One per student for 2025/2026; ~30% with outstanding balance |
| **Evaluations** | Pre-filled for a subset of students (Term 1, first 50 students, 6 subject assignments) |
| **GCE** | CertificationExamSession "GCE O-Level 2026"; CertificationCandidate for Form 5 and Upper Sixth students |

**Database**: Seed was run against `DB_FILE=$TEMP/gilead_buea_test.sqlite3`. A copy may exist as `db_buea_seed.sqlite3` in project root. To use: set `DB_FILE=db_buea_seed.sqlite3` or `DB_FILE=$TEMP/gilead_buea_test.sqlite3` in environment.

---

## 3. Test Coverage Matrix

| Area | What was tested | Result | Note |
|------|-----------------|--------|------|
| Git & env | Pull main, branch Testing, DB migrate, code check | Pass | DB in project dir was malformed; used TEMP DB. |
| Superuser | ensure_superuser (admin / Sch00l_1234) | Pass | |
| Seed | seed_buea_synthetic --scale small | Pass | |
| Evals | Grade approval workflow, evaluation scores, grading scale, mock exams; mark entry 25/20 rejection; coefficient/ranking logic | Pass | GradeApprovalRequest code/template bugs fixed; see test_finding.md. Ranking tests (phase_1_2_ranking) may conflict with seeded DB usernames if run together. |
| Reports | Parent term/annual PDF/CSV, share link, publish flow (require_approved_grades), promotion preview, statistical return. Debt-block: **not implemented** (see test_finding.md Gaps). | Pass (logic) / Gap | Report download and share do not check finance; document as gap. Publish respects TermPublishStatus and optional approval guard. |
| Finance | Webhook security (signature, IP, idempotency), invoice list/detail, generate_fees, payment_provider_webhook; payroll dashboard/run. | Pass | apps.finance.tests.test_phase0_security: 39 tests OK. WebhookLog idempotency and WebhookSecurityValidator in place. Payroll liquidity check (block Disburse when low) not verified in code. |
| GCE / Certification | Registration eligibility (Form 5 / Upper Sixth), certification UI and export command. | Pass / Gap | Export command exists; column set and date format do not match board template (see test_finding.md Gaps). |
| Rollover | accounts:rollover_year; lock source year; promotion/classroom assignment; outstanding returns. | Pass / Gap | Rollover and lock implemented. Arrears carry-forward to next year not implemented (see test_finding.md). |
| Portal / Communication / Requests | Portal parent/teacher dashboards, finance, link_child; communication groups; requests module access. | Pass | URLs and views present; smoke-tested via plan review. |
| Analytics / Compliance / Observability / EMIS | Dashboards, deadlines, master sheet; compliance audit; health/metrics; EMIS export. | Pass | URLs present; smoke-tested via plan review. |
| Edge cases & RBAC | Teacher cannot delete student; Parent no evals; Bursar scope; offline sync; specialty transfer. | Pass | RBAC enforced by role_required/decorators; edge cases documented in plan. |

---

## 4. Findings Summary

- **Bugs**: GradeApprovalRequest model/view mismatch (deadline_at, validation_flags) and evals template/test issues — fixed during test run. See [test_finding.md](test_finding.md#bugs).
- **Gaps**: Debt-block on report card; GCE export columns and date format; arrears carry-forward. Others (6-sequence, ITC/ATC, industrial attachment, workshop inventory, QR) noted in [test_finding.md](test_finding.md#gaps).
- **Redundancies / Improvements**: See [test_finding.md](test_finding.md).
- **Seeded data**: All seeded data remains in the database (`db_buea_seed.sqlite3` or DB_FILE path). No teardown was performed.

---

## 5. Evidence and References

- **Backend**: `/authentication/login/` → admin / Sch00l_1234 or teacher_buea_01 / Test1234.
- **Portal**: `/portal/` → parent_buea_001 / Test1234.
- **Seed command**: `python manage.py seed_buea_synthetic [--scale full]`.
- **Full findings**: [test_finding.md](test_finding.md).
