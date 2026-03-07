# Rollover Plan vs Buea 2026 SMS Workflow

This document compares **our current rollover implementation** to the **Buea 2026 school management system** rollover workflow (finalize current year → promotion & transition → set up new year → go-live, plus static vs session data, financial carry-over, and archive).

---

## Side-by-side overview

| Buea 2026 workflow | Our implementation | Gap / suggestion |
|-------------------|--------------------|------------------|
| **1. Finalizing the current year** | | |
| Grade hard lock by deadline; after rollover, prior-year edits are manual/invasive | **Term-level lock:** Marks entry is blocked when term is **published** (`TermPublishStatus`). **Year-level:** `AcademicYear.is_locked` blocks **rollover from** that year and **grade edits** for that year: teacher marks entry and OCR apply both check `year.is_locked` and return 403 / no-op. | **Done:** Evals enforce year hard lock when `academic_year.is_locked`. |
| Archive: permanent copy of report cards/transcripts (Report Card History) | ReportCard model and PDF generation exist; reports are generated and can be published. No explicit “read-only archive” or “snapshot of year” for querying old transcripts. | **Add (optional):** “Archive year” step: snapshot or mark year as archived so transcript queries can target “archived” data; or document that “locked year + report cards” is the archive. |
| Financial reconciliation: clear pending balances; verify MINESEC portal payments | Invoices, payments, balance tracking (e.g. `balance_amount`, MoMo) exist. No rollover-specific “reconcile before rollover” or MINESEC verification step. | **Add (optional):** Pre-rollover checklist item “Financial reconciliation” (e.g. report of outstanding balances); optional link to MINESEC/portal verification. |
| **2. Promotion & transition** | | |
| Student promotion: auto-advance by grades (e.g. Form 5 → Lower Sixth) | **Promotion status** (PROMOTED / REPEAT / DEMOTED) from `PromotionRule` (e.g. 10/20). **Rollover wizard:** operator assigns “next class” per student; **suggestion** = same **classroom name** in target year (e.g. Form 5A → Form 5A). No automatic “Form 5 → Lower Sixth” mapping. | **Enhance (optional):** “Promotion level mapping” (e.g. Form 5 → Lower Sixth, CAP → Probatoire) so suggested next class is the **promotion** class, not same name. Same-name suggestion already supports “repeating” (Form 5A → Form 5A in new year). |
| Buea technical: CAP → Probatoire | Certification supports technical (OBC, CAP/Probatoire/Bac). Rollover does not special-case technical levels. | Same as above: optional mapping “CAP classroom → Probatoire classroom” for target year. |
| UIN persistence: student UIN unchanged; history and fees follow | StudentProfile (and certification `unique_identifier` / matricule) persist; we do not re-create identity on rollover. Student id and profile stay; only `academic_year` and `classroom` change. | **OK.** Document that “UIN” = admission_number / unique_identifier / student id; all stay. |
| Graduation / deactivation: final year (e.g. Upper Sixth) → “Graduated” → alumni; departing staff deactivated | StudentProfile has status **ALUMNI**. Rollover does **not** auto-move final-year students to alumni or set status to “Graduated”. No staff deactivation in rollover. | **Add (optional):** In rollover, optional “Graduate final-year students” (e.g. mark as ALUMNI and optionally set classroom to null or “Graduated” class). Optional “Deactivate staff” flow (separate from rollover). |
| **3. Setting up the new year** | | |
| New calendar: create 2026-2027, set “Future” or “In Rollover” (hidden from students/parents) | AcademicYear has `name`, `start_date`, `end_date`, `is_active`. No “Future” or “In Rollover” status. | **Add (optional):** Status or flag on AcademicYear (e.g. `status = DRAFT | ROLLOVER | ACTIVE`) so new year can be hidden until go-live. |
| Timetable & resource sync: copy schedule (classrooms, time slots) into new year | **Clone year** copies terms, **classrooms**, subject assignments, promotion rules. **Scheduling** (Room, TimeSlot, Schedule) exists in code; clone does **not** copy timetables/schedules. | **Add (optional):** “Clone timetable” or include schedule copy in clone; or document “adjust timetables in new year after clone”. |
| LMS / first grading period: activate so teachers can upload syllabi | Terms are cloned; “first grading period” is just “first term” of new year. No explicit LMS activation step. | **OK** if “first term” = first grading period; optional “Activate term” or “Open for entry” flag. |
| **4. Final certification & go-live** | | |
| Data verification: sample check promoted students / rosters | Rollover page shows **all** students with promotion status and next class; operator can review before Apply. No formal “verification sample” report. | **Enhance (optional):** “Rollover verification” report (sample or full list) for export/sign-off. |
| “Finalize Rollover”: new year becomes Active; SMS to parents (new class, fees) | We do **not** auto-set the **active** year on rollover; no SMS on rollover. | **Add (optional):** After rollover, optional “Set target year as active” and optional “Send SMS/email to parents” with new class and fee info. |
| **Static vs session data (Buea)** | | |
| Carries over: bio-data, transcripts, financial credit, contacts, library history | Student/teacher profiles, report cards, invoices/payments, guardian links persist. We do not “reset” attendance or discipline on rollover. | **OK.** Identity and history carry; only `academic_year` and `classroom` change for students. |
| Resets: attendance, term grades (move to archive), discipline, timetables, fee requirements (new invoices) | We do **not** reset attendance or discipline. **Grades:** Evaluations stay in DB (linked to year/term); “current gradebook” is filtered by active year/term, so old grades are “out of view” but not deleted. **Invoices:** New year typically gets new invoices; no automatic “balance forward” on new invoice. | **Clarify:** “Resets” in Buea = “not shown in current view” or “zeroed for new year”. We can document: term grades stay for transcripts; current view = active year. **Add (optional):** “Balance forward” on new year invoice (debt/credit from previous year). |
| **Financial carry-over (Buea)** | | |
| Balance forward: debt or credit from 2024/2025 on 2025/2026 invoice | Invoices are per profile/year/term; we do not auto-apply prior-year balance to new year invoice. | **Add (optional):** “Balance forward” line or opening balance on first invoice of new year (from previous year’s closing balance). |
| Payment integration (MTN MoMo) for clearing before September | Payments (including MoMo) exist; no rollover-specific “cleared before rollover” check. | **Add (optional):** Pre-rollover report “Outstanding balances” and/or “Block rollover if unpaid” option. |
| **Teacher & resource mapping** | | |
| Teacher profiles stay; course assignments wiped and re-mapped for new year | TeacherProfile persists. **SubjectAssignment** is year/term/classroom/specialty/subject (no teacher on it); **TeacherAssignment** (if present) links teacher to subject assignment. Clone copies **SubjectAssignment** for new year; teachers are not auto-assigned to new year’s assignments. | **OK.** Operators re-assign teachers to classes for new year (existing admin or backend). Optional: “Clone teacher assignments” from previous year. |
| Inventory carry-over (technical): workshop quantity; reset Usage Log | Asset/inventory models exist; no rollover step for “carry quantity, reset usage log”. | **Add (optional):** Inventory rollover (carry quantities, reset usage for new year). |
| **Archive & go-live sequence** | | |
| Snap-shot archive: read-only copy of old year before finalize | We have **is_locked**; no separate “snapshot” or “archive” table. Locked year = no more rollover from it; we could treat it as “frozen” for reporting. | **Add (optional):** Explicit “Archive year” (e.g. copy key data to read-only store) or document “locked year + reports = archive”. |
| Backup → Promotion → Financial init → Verification → Activation | We have: **Promotion** (rollover wizard). We do not trigger **backup**, **financial init** (new fees), or **activation** (set active year) from rollover. | **Add (optional):** Rollover checklist or post-rollover steps: “Backup recommended”, “Generate new year invoices”, “Set new year as active”, “Notify parents”. |

---

## Summary: what we have vs what we’d add

**Already aligned with Buea**

- **Promotion engine:** PromotionRule (e.g. 10/20), PROMOTED/REPEAT/DEMOTED, annual average; rollover wizard with per-student next-class choice and same-name suggestion for repeaters.
- **UIN / identity:** Student profile and identifiers persist; only academic_year and classroom change on rollover.
- **Clone year:** Terms, classrooms, subject assignments, promotion rules copied to new year; classroom codes made unique.
- **Lock year:** `AcademicYear.is_locked`; blocks rollover from that year; optional “lock after rollover”.
- **Static data:** Bio-data, contacts, report history, invoices/payments stay; no destructive reset of identity or history.
- **Finance base:** Invoices, payments, balance tracking, MoMo; no balance-forward or rollover-specific reconciliation yet.

**High-value additions (Buea-style)**

1. **Grade hard lock at year level:** **Done.** In evals, if `academic_year.is_locked`, marks entry (and OCR apply) are blocked for that year.
2. **Optional “Finalize rollover” behaviour:** After rollover, optional “Set target year as active” and optional “Notify parents” (SMS/email) with new class and fees.
3. **Optional balance forward:** On first invoice(s) of new year, carry prior-year closing balance (debt or credit) as “balance forward” (Cameroon/Buea expectation).
4. **Optional graduation step:** In rollover (or separate action), mark final-year students as “Graduated” / ALUMNI and optionally move to alumni list.

**Nice-to-have**

- Year status: DRAFT / ROLLOVER / ACTIVE so new year stays hidden until go-live.
- Promotion level mapping: e.g. Form 5 → Lower Sixth, CAP → Probatoire for suggested “next class”.
- Pre-rollover checklist: e.g. “Financial reconciliation”, “Archive/backup”, “Verification report”.
- Snapshot/archive: read-only copy of year for transcript queries; or document “locked year = archive”.
- Clone timetable: copy schedule to new year or document manual adjustment.
- Inventory rollover: carry quantities, reset usage log for new year.

---

## Flow comparison (one sentence each)

| Buea 2026 | Our system |
|-----------|------------|
| Finalize current year (grade lock, archive, reconcile) then promotion then set up new year then go-live. | Clone year (structure) → Rollover (move students, optional lock) → manual “set active year” and “new invoices”; term publish already locks grades; year lock blocks rollover and (if we add it) grade edits. |
| Promotion by rule (e.g. 10/20); repeaters same level; UIN persists; graduates → alumni. | Same rule and status; operator picks next class (suggestion = same name); identity persists; alumni is manual or optional step. |
| Balance forward and MTN clearing before new session. | No balance forward yet; payments/MoMo exist; optional reconciliation and balance forward. |
| New year “Future” until finalize; then Active + parent SMS. | New year created then cloned; no status; optional “set active” and “notify parents”. |

So: **our rollover already covers “promotion engine”, UIN persistence, clone structure, lock year, and static data.** To align fully with the Buea 2026 description we’d add **year-level grade lock when year is locked**, optional **go-live** (set active + notify parents), optional **balance forward**, and optional **graduation/alumni** and **year status** for “Future” vs “Active”.
