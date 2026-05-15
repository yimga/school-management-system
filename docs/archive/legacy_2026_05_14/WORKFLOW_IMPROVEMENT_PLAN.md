# Workflow Improvement Plan
## Full Student Lifecycle & Cameroon/Buea Alignment

**Date:** January 28, 2026  
**Purpose:** Map the SMS against the full operational backbone (pre-year → active year → assessment → year-end → alumni) and Cameroon/Buea workflows; identify gaps and prioritize improvements.

---

## Executive Summary

The system already covers **year setup**, **onboarding**, **marks entry**, **report publishing**, **communication**, **documents**, **certification (GCE/BAC/BEPC/CAP)**, and **settings**. To align with the full “operational backbone” and Buea/Cameroon reality, the plan below adds **admissions funnel**, **scheduling UI**, **intervention tracking**, **year-end lock & rollover**, **inventory/asset collection**, **alumni module**, **Cameroon-specific workflows** (three-term, sequences, deliberation, statistical returns, centre vs attached), and **mobile money / E-Reg** integration where missing.

---

## 1. Pre-Academic Year Planning (The Setup)

| Area | Current State | Gap / Improvement |
|------|----------------|-------------------|
| **Admissions & enrollment** | Student onboarding wizard; admin create; guardian invites. No “inquiry → application → enrolled” funnel. | **Add:** Inquiry/lead model; application status (pending, accepted, rejected); enrollment funnel dashboard (leads → applications → enrolled); optional online application form with document upload. |
| **Resource & curriculum** | Academic year, terms, classrooms, departments, specialties, subjects, subject assignments (coefficients). | **Improve:** Course catalog view for operators; “clone previous year” for classrooms/subjects; explicit link from Workflow Center to “clone year.” |
| **Dynamic scheduling** | **Present:** `apps/academics/scheduling.py` (Room, TimeSlot, Schedule, ScheduleEntry, TimetableGenerator, constraints). | **Improve:** Admin/backend UI to create and publish timetables; teacher/student timetable view in portal; conflict report; optional “Wednesday afternoon” block for co-curricular (Buea). |
| **Financial planning** | Invoices, fee structures, payment methods (MTN MoMo, Orange in ledger). No tuition revenue forecast. | **Add:** Simple revenue forecast by term (expected students × fee); “fee structure for new year” setup checklist in Workflow Center. |

**Suggested deliverables (Phase A)**  
- Inquiry/Application models + list view + optional public application form.  
- “Clone previous year” for academics + one-click in Workflow Center.  
- Timetable UI: create/publish schedule, view by teacher/class, conflict check.  
- Revenue forecast widget (configurable formula).

---

## 2. Active School Year Management (The Core)

| Area | Current State | Gap / Improvement |
|------|----------------|-------------------|
| **Student information** | StudentProfile (demographics, health placeholder, behavioral via discipline if present); single source of truth. | **Improve:** Explicit “health” and “conduct” fields or modules; transfer certificate / previous school fields for Buea transfers. |
| **Attendance & monitoring** | Attendance models exist; teacher/staff entry. | **Improve:** QR/biometric placeholder or integration point; “absence alert” to parent (SMS/WhatsApp) as in Buea workflow; morning roll-call summary. |
| **Engagement portals** | Parent/teacher dashboards; messages; contact requests; announcements. | **Improve:** Homework/events notifications; “instant alert on absence” option in site settings. |
| **Financial operations** | Invoicing, payments, MTN/Orange in ledger; receipt generation. | **Improve:** Unique payment code per student (anti-fraud, Buea); MoMo reconciliation status in parent view; optional payment reminder automation. |

**Suggested deliverables (Phase B)**  
- Transfer certificate / previous school on StudentProfile; optional “national matricule” (MINESEC) field.  
- Absence alert: configurable “notify parent on first absence” (email/SMS/WhatsApp).  
- Unique payment reference per invoice/student for MoMo.  
- Revenue/payment reconciliation report for bursar.

---

## 3. Assessment and Mid-Year Reporting

| Area | Current State | Gap / Improvement |
|------|----------------|-------------------|
| **Digital gradebooks** | Evaluations, subject assignments, coefficients; term/sequence support; Cameroon report styles (moyenne, promotion). | **Improve:** Explicit “sequence” (SEQ1–SEQ6) labels in UI and reports; through-year / multi-term view for “single summative” style. |
| **Intervention tracking** | `AdvancedAnalyticsService.identify_at_risk_students()`; ML risk; analytics dashboard. | **Improve:** Dedicated “Intervention” or “At-risk” list with status (referred, in progress, closed); optional RTI/MTSS tiers; link to student profile and recent grades. |
| **Mid-year “reality check”** | Term reports; promotion rule (e.g. 10/20). | **Improve:** Mid-term promotion preview (would promote / would repeat); optional “council” flag for borderline (e.g. 9.5/20) for Deliberation Council. |

**Suggested deliverables (Phase C)**  
- Sequence labels (SEQ1–SEQ6) in marks entry and report templates.  
- Intervention module: at-risk list, status workflow, notes.  
- “Promotion preview” report (by class) and “borderline list” for council.

---

## 4. Year-End Processing & Transition

| Area | Current State | Gap / Improvement |
|------|----------------|-------------------|
| **Examination management** | Certification (GCE/BAC/BEPC/CAP); sessions, candidates, CA export, presets; matricule, CIN, MTN txn. | **Improve:** Hall ticket / individual timetable print view; exam attendance tracking; final GPA/CGPA on report if not already. |
| **Year-end rollover** | PromotionRule (e.g. 10/20); `get_promotion_status()`; report shows promotion status. No “lock year” or bulk “promote to next class.” | **Add:** “Lock year” (no more grade edits); “Rollover” action: bulk promote/repeat by rule + optional “deliberation” overrides; archive term/year. |
| **Comprehensive reporting** | Term/annual reports; analytics; compliance. | **Improve:** “Annual Statistical Return” for MINESEC/Regional Delegation (Buea): gender, success rates, teacher-student ratio; export PDF/Excel. |
| **Inventory & asset collection** | Finance `Asset` model (generic). No device-return or textbook checklist. | **Add:** “Device return” or “Resource return” checklist (e.g. tablet/laptop/textbook) per student; block promotion by “outstanding items” optional rule. |

**Suggested deliverables (Phase D)**  
- Hall ticket / exam timetable template for certification candidates.  
- Year-end: “Lock year” flag; “Rollover” wizard (preview → apply promote/repeat); optional “deliberation” override list.  
- Statistical return report (configurable columns) for regional submission.  
- Resource return checklist (model + UI); optional “block promotion if not returned.”

---

## 5. Post-Graduation & Alumni

| Area | Current State | Gap / Improvement |
|------|----------------|-------------------|
| **Alumni** | StudentProfile has status `ALUMNI`; no dedicated workflow. | **Add:** Alumni list/filter; “Move to alumni” bulk action; optional alumni portal (view transcript, update contact); transcript request workflow. |

**Suggested deliverables (Phase E)**  
- Alumni filter and “Graduate / move to alumni” action.  
- Optional: alumni self-service transcript request and audit log.

---

## 6. Cameroon / Buea–Specific Workflow

| Area | Current State | Gap / Improvement |
|------|----------------|-------------------|
| **Three-term structure** | Terms exist; no fixed “second Monday of September” or Buea labels. | **Improve:** Term templates (e.g. “Term 1: Sept–Dec”); optional “Buea default” terms; Workflow Center tip. |
| **Sequences (6)** | Marks and reports support terms/submissions; “sequence” mentioned in docs. | **Improve:** Sequence (1–6) as first-class in UI and reports; “Sequence 1 & 2” (Term 1) in report card text. |
| **Moyenne / coefficient** | SubjectAssignment.coefficient; reports compute weighted average; PromotionRule (10/20). | **OK;** ensure report labels “Moyenne” / “Terminal Average” (already in Cameroon templates). |
| **Competency-based (CBC)** | CompetencyRubric, CompetencyItem, StudentCompetencyAssessment (evals). | **Improve:** CBC setup guide in KB; optional “Learning situation” or competency column in report. |
| **GCE / E-Registration** | Sessions, candidates, CIN, matricule, MTN txn, CA export; presets GCE/OBC. | **Improve:** Doc “Approved vs attached centre”; “Data[CentreNo].zip” style export name; optional “Host centre” link for attached schools. |
| **Deliberation council** | No explicit “council” or “grace” workflow. | **Add:** “Deliberation” list (e.g. 9.0–10.0); Principal “grace” flag per student; store in override or note; show on report. |
| **Digital report cards** | Term/annual reports; publish to parent; email. | **Improve:** WhatsApp option; QR on report (link to verify); “Digital report sheet” wording in templates. |
| **Statistical return** | No dedicated MINESEC-style return. | **Add:** Report: success rates, gender ratio, teacher-student ratio, by class/level; export for Regional Delegation. |
| **Textbook / resource recovery** | No checklist. | **Add:** As in §4 (inventory/asset collection). |
| **Offline / sync** | OfflineMarkEntry, mobile sync APIs. | **Improve:** Doc “local server + cloud sync”; optional sync status in UI. |
| **Multilingual** | Localization; report styles (EN/FR). | **Improve:** Ensure report can be generated in French and English; language selector for report. |

**Suggested deliverables (Phase F)**  
- Term template “Buea (3 terms)”; sequence labels in UI and reports.  
- KB: “Approved vs attached centre”; export filename `Data[CentreNo].zip`; Host centre field optional.  
- Deliberation: borderline list + “grace” override; show on annual report.  
- Statistical return report + MINESEC-style export.  
- Resource return checklist (§4).  
- Optional: WhatsApp report notification; QR on report.

---

## 7. Strategic Setup (Policy & Rules)

| Area | Current State | Gap / Improvement |
|------|----------------|-------------------|
| **Policy & rules** | Grading scales; promotion rule; RBAC; grade approval. | **Improve:** Single “Policy” or “Academic rules” page (promotion threshold, grading scale, who can edit grades); link from Workflow Center. |
| **Resource mapping** | Asset categories; no “budget vs physical” map. | **Optional:** Asset/budget mapping or “needs” list for next year. |
| **Faculty workload** | TeacherProfile; subject assignments. | **Improve:** “Faculty workload” report (hours/courses per teacher); optional max hours constraint in scheduling. |

**Suggested deliverables (Phase G)**  
- “Academic rules” summary page (promotion, grading, approval).  
- Faculty workload report; optional constraint in TimetableGenerator.

---

## 8. Prioritized Roadmap (Summary)

| Phase | Focus | Priority | Deliverables |
|-------|--------|----------|---------------|
| **A** | Pre-year | High | Inquiries/applications; clone year; timetable UI; revenue forecast. |
| **B** | Core operations | High | Transfer/matricule; absence alert; unique payment code; reconciliation. |
| **C** | Assessment | Medium | Sequences in UI; intervention module; promotion preview + borderline. |
| **D** | Year-end | High | Lock year; rollover wizard; statistical return; resource return checklist; hall ticket. |
| **E** | Alumni | Medium | Alumni filter/actions; optional transcript request. |
| **F** | Cameroon/Buea | High | Term/sequence labels; approved vs attached doc; deliberation; MINESEC return; checklist. |
| **G** | Policy & faculty | Medium | Academic rules page; faculty workload report. |

---

## 9. Non-Rigid Design Notes

- **Workflow Center** already presents a single lifecycle (setup → onboarding → marks → reports → documents → certification → settings) and states that it fits Cameroon general and technical (GCE, BAC, BEPC, CAP) without a rigid sequence.  
- New steps (e.g. “Admissions funnel,” “Year-end rollover,” “Alumni”) can be added as **optional** steps or links so schools that do not use them are not forced into a fixed order.  
- **Certification** remains optional per academic year; “approved vs attached” centre is documentation and optional fields, not a change to core logic.  
- **Three-term / six-sequence** can be configured via existing terms and evaluation types; labels and templates make them visible without hard-coding Buea.

---

## 10. Next Steps

1. **Stakeholder:** Choose phase(s) for the next sprint (e.g. A + D + F for “setup + year-end + Cameroon”).  
2. **Tech:** For chosen phase, break deliverables into tickets (models, APIs, UI, docs).  
3. **Docs:** Update Workflow Center and KB with new steps and links as each deliverable ships.  
4. **QA:** Test with a Buea-style calendar (three terms, sequences, GCE, mock then final) and with an “attached” school scenario if applicable.

---

*This plan aligns the SMS with the full operational backbone and Cameroon/Buea workflows while keeping the system flexible and non-rigid.*
