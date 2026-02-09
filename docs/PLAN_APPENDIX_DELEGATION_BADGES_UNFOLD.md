# Plan Appendix: Delegation, Badges, CBA Builder, Unfold (Full Specification)

This document expands the main plan with the full delegation/proxy system, admin master control, badge system (staff and student), CBA syllabus builder, approval flow detail, and Django Unfold backend. **Everything is configurable from the admin panel; no hardcoding. The system is region-agnostic (e.g. usable in Cameroon and elsewhere).**

---

## 1. Delegation & Proxy System (Full)

### 1.1 User profile: Out of Office / Delegation

- Section in profile/settings: **"Out of Office / Delegation"** (label configurable in admin).
- **Assign proxy:** Dropdown of colleagues; list filtered by admin-configured "who can delegate to whom" rules.
- **Date range:** Start date, End date. At configurable time on end date (e.g. 00:00 or 23:59), permissions revert.
- **Extend:** Delegator or Admin can extend (e.g. `extended_end_date`).
- **Scope:** Checkboxes for which permissions to delegate (Syllabus Approvals, Discipline Records, Financial Approvals, etc.). List of delegatable permissions is **configurable in admin**.

### 1.2 Dean (Approver) delegation

- Delegate sees toggle/tab **"Acting as [Dean's Name]"**. Can view, comment, approve syllabi.
- Audit: "Approved by [Acting Dean] on behalf of [Dean Name]"; store `actor=delegate`, `acting_for=delegator` in audit table.

### 1.3 Teacher (Creator) delegation

- Teacher delegates **Course Management** to substitute for selected classes.
- Substitute gets temporary access to teacher’s dashboard for those classes; can upload syllabus or use builder.
- Class cards on substitute’s dashboard show **"Covering"** or **"Substitute"** badge (label configurable).

### 1.4 Emergency override

- Principal/Admin has **Emergency Override** in admin to manually assign a proxy to any account. Audit who triggered it and for whom.

### 1.5 Notifications

- When delegation starts: optionally notify delegate by **email** and/or **SMS** (configurable: Email / SMS / Both / Off). SMS helps in low-connectivity regions.

### 1.6 Conflict prevention

- Configurable: **Block delegator** from taking delegated actions while OOO (e.g. no double-approvals).

### 1.7 "While You Were Away" (automation)

- **Summary:** e.g. "12 syllabi approved by Vice-Principal; 2 rejected."
- **Flagged issues:** e.g. "3 teachers missed submission deadlines."
- **Critical actions:** e.g. "Vice-Principal signed off on Form 5 Physics Lab."
- **Review Decisions:** Link to items signed by proxy (`acting_for=current_user`).
- **Urgent filter:** Only items delegate rejected or flagged.
- **Bulk review:** "Acknowledge All."
- **Principal Override:** Configurable window (e.g. 48 hours) after return to reverse or flag an approval (with reason; audit).

### 1.8 Auto-archiving when delegation ends

- Bundle proxy actions into PDF/report; save in Admin Audit Logs.
- Document Library: approved syllabi moved to permanent library; signature "Original Owner: Principal | Approved by: Vice-Principal (Proxy)". Teacher sees "Approved by [Proxy Name] (Acting HOD)."

### 1.9 Technical

- **Model:** `Delegation`: `delegator`, `delegate`, `start_date`, `end_date`, `extended_end_date`, `is_active`, `scope` (JSON or M2M), `reason`/`notes`.
- **ProxyLog / DelegationActionLog:** `delegation`, `action_taken`, `object_id`, `timestamp`, `actor`, `acting_for`.
- **Helper:** `get_effective_approvers(workflow_key)` uses configurable roles + delegate substitution.
- **Celery Beat:** Daily task to set `is_active=False` when past end date; optionally email Summary Report to delegator.

---

## 2. Admin Panel – Delegation Master Control

All configurable; no hardcoding.

- **Delegation Management** module: Role mapping (who can delegate to whom), permission toggles (which actions are delegatable), audit log (active delegations + history).
- **Global settings:**

| Feature | Admin control | Description |
|--------|----------------|-------------|
| Max duration | e.g. 14 days | Max days per delegation. |
| Auto-revoke | On / Off | Revoke proxy at end date. |
| Approval proxy | On / Off | Delegate can approve syllabi (and other as configured). |
| Summary report | Automatic / Manual / Off | "While You Were Away" on return. |
| Notify delegate on start | Email / SMS / Both / Off | When delegation starts. |
| Block delegator while OOO | On / Off | Prevent double-approvals. |

- **Emergency override:** Admin/Principal can assign proxy to any account.
- **Live map:** Dashboard of who is OOO and who is covering (delegator → delegate, end date).

---

## 3. Approval & Document Library Flow (Detailed)

- **Dean review screen (split view):**
  - **Left:** Syllabus (builder data or uploaded PDF).
  - **Right:** Checklist (configurable): e.g. "Meets national standards?", "Assessment dates clear?"
- **Approve:** System generates final PDF with **digital school stamp** (configurable template). Status → APPROVED; sync to Document Library.
- **Revision:** Dean highlights section (or attaches comment); status → NEEDS_REVISION; teacher resubmits.
- **Archiving:** On approval, file is mirrored in Document Library (structure: Year > Department > Subject, or configurable). Teacher/Student dashboards updated. If approved by proxy: show "Approved by [Proxy Name] (Acting HOD)."

---

## 4. CBA Syllabus Builder (Cameroon Standard – Configurable)

MINESEC/MINEDUB Competence-Based Approach (CBA) can be supported via **configurable** builder schema (so other regions can use different schemas).

- **JSON schema (configurable in admin):** e.g.
  - **Families of Situations:** e.g. Family & Social Life, Economic Life, Citizenship.
  - **Competencies:** Subject-specific, transversal, life competencies.
  - **Resources:** Cognitive, affective, psychomotor (Context, Aptitude, Attitudes).
  - **Assessment Grid:** Integrated formative assessment strategies.
- **Admin:** Mandatory sections (e.g. "Competence-Based Approach" section) defined in config; teachers cannot delete them. Section labels and order configurable (no hardcoded "CBA" in code; region-specific config).

---

## 5. Teacher Multi-Subject Dashboard (Recap)

- **Grid of course cards:** Subject, Class/Form, **Syllabus Status** badge (Missing, Draft, Pending, Approved).
- **Action hub (per card):** Guided Builder | Fast Upload (drag-and-drop Word/PDF/scan) | Clone (e.g. Form 3A → 3B).
- **Preview:** "View as Student/Dean" – watermarked PDF in popup.
- **Delegated classes:** Shown with "Covering" or "Substitute" badge when user is acting for another teacher.

---

## 6. Badge System (Staff & Student – Virtual & Physical)

### 6.1 Principles

- **Configurable:** Badge types, criteria, labels, and designs are set in admin (no hardcoded "Honor Roll" or "Syllabus Master" in code). Region-agnostic.
- **Trigger-based:** Badges are created by **events** (signals / automation), not manually uploaded, so they are authentic and auditable.

### 6.2 When badges are created (triggers)

| Moment | Trigger | Result (examples – configurable) |
|--------|---------|----------------------------------|
| **Onboarding** | Post-save on User/Staff/Student profile | Identity badge + QR code + "Active Member". |
| **Milestone** | Syllabus status → APPROVED | Teacher: e.g. "Syllabus Master" (label configurable). |
| **Milestone** | Student average e.g. ≥ 16/20 (threshold in admin) | Student: e.g. "Honor Roll" on parent portal. |
| **Administrative** | Delegation becomes active (start date reached) | Delegate’s profile badge temporarily shows e.g. "Acting Principal"; reverts when delegation ends. |

### 6.3 Staff badge (virtual & physical)

- **Virtual (in-platform):**
  - Shown on staff profile/dashboard.
  - Optional: border/style by seniority or status (e.g. "Approved Syllabus") – configurable.
  - **Dynamic QR code:** Scan → verification page (current employment, not suspended). QR payload: e.g. signed token (user id + school + expiry); no hardcoded school name in URL.
- **Physical:**
  - Admin action: **"Print ID Card"** (single or bulk). Backend: ReportLab or WeasyPrint; PDF to standard ID size (e.g. CR80: 85.60 × 53.98 mm).
  - **Front (configurable fields):** Photo, Full Name, Department, Employee ID, School Year, Role Tag (e.g. TEACHER, DEAN).
  - **Back (configurable):** Emergency contact, Blood group (optional; common in some regions), School motto/QR. All field labels and visibility configurable in admin.

### 6.4 Student badges in parent profile

- **Achievement-based (criteria configurable):**
  - e.g. Attendance badge: green if attendance > 95% (threshold in admin).
  - e.g. Academic: "Honor Roll" if average above X/20 (X configurable).
  - e.g. Conduct: "Disciplined" if zero conduct reports (rule configurable).
- **Parent view:** Each child has a **"Digital Medal Case"** – badges with optional evidence link (e.g. click badge → specific report or date).
- **Info on badge/card (configurable):** Student ID (for fees/MoMo), Class/Form, Status (Paid, Active, On Leave), QR linking to e.g. digital report card or verification URL.

### 6.5 Delegation + badge

- When Vice-Principal is "Acting Principal," their **virtual badge** temporarily shows e.g. "Proxy Principal" (label configurable). When delegation expires, badge reverts automatically.

### 6.6 Advanced (optional phases)

- **Access control:** Optional RFID/NFC on physical badges for room access (separate integration; configurable on/off).
- **Anti-counterfeit:** Optional holographic/tactile on physical cards (production step; configurable).
- **QR scan log:** Each time a badge QR is scanned (e.g. at gate), log time and optional location → **heat map** in admin (configurable).
- **Teacher professional:** Optional badges: e.g. "CBA Certified," "Peer Collaboration" (nomination workflow), "100% Syllabus Coverage," "Zero Unexcused Absences" – all trigger-based and configurable.
- **Student:** Optional competency-based medals ("Critical Thinker," "Public Speaker") from teacher evaluations; **real-time alert to parent** when badge earned; optional **digital portfolio** / social sharing (configurable).

### 6.7 Admin

- **Badge settings:** Design, colors, which fields appear on virtual/physical card – configurable in admin.
- **Bulk print:** Admin selects students/staff and runs "Generate Physical ID Cards" (PDF).
- **Offline verification:** Optional daily cache of active staff/student list + QR hashes for guards to verify offline (configurable; important for low-connectivity).

### 6.8 Technical

- **Model(s):** e.g. `Badge` (or `StaffBadge` / `StudentBadge`): type (configurable), user/student, criteria_met (JSON), image/QR, issue_date, expiry_date, is_physical_printed. Optional `BadgeType` model: code, label, criteria_rule (e.g. JSON or reference to a rule), image_template.
- **Signals:** Post-save on Syllabus (status=APPROVED), on Student evaluation (average), on Delegation (start/end) → create/revoke badges via configurable rules.
- **QR:** Generate with e.g. `qrcode` library; store signed token (user id, school id, expiry); verification view checks DB and returns current status.

---

## 7. Django Unfold Backend

- **Custom actions:** e.g. "Approve selected syllabi" in Unfold admin; checks effective approver (role + delegate).
- **get_queryset:** For approval list, if current user is a delegate (active Delegation where delegate=request.user), include owner’s items so delegate sees "their" queue (e.g. `Q(teacher=request.user) | Q(teacher=active_proxy.owner)`).
- **ProxyLog:** Log every approval/action by delegate with `acting_for=delegator` for catch-up and audit.
- **Celery Beat:** Daily task to expire delegations (`end_date` / `extended_end_date` passed → `is_active=False`); optionally send Summary Report email to delegator.
- **SyllabusConfig (or SiteSettings):** e.g. `allow_teacher_uploads` (True: show Upload; False: builder-only). Configurable per school.
- **Tab links / sidebar:** e.g. "My Syllabi," "Pending My Approval," "Delegated to Me" (labels configurable).
- **Document Library sync:** On syllabus approval, Celery task or signal to generate final PDF (WeasyPrint), upload to storage, create PortalFeatureItem; optional watermark/stamp from configurable template.

---

## 8. Phased Implementation (Complete)

| Phase | Item | Description |
|-------|------|-------------|
| 1 | Admin configurability | Approval roles, syllabus sections, institutional text, document categories – all from admin. |
| 1 | Delegation model & UI | Delegation/ActingAssignment model; profile "Out of Office"; assign proxy, dates, scope; extend. |
| 1 | Approval override | get_effective_approvers(workflow); delegate substitution; no hardcoded roles. |
| 1 | Admin delegation control | Role mapping, permission toggles, max duration, auto-revoke, live map, emergency override. |
| 1 | Catch-up & ProxyLog | Log actions by delegate; "While You Were Away" view; optional Principal Override window. |
| 2 | Syllabus Builder | CourseSyllabus, builder + upload, preview, approval queue, Document Library sync, cloning. |
| 2 | CBA schema (configurable) | JSON schema for builder sections (e.g. CBA); mandatory sections from config. |
| 2 | Dean split-screen & stamp | Split syllabus + checklist; approve → PDF with school stamp; archiving to Document Library. |
| 3 | Document Library structure | Categories/folders (e.g. Essential Student Records, Administrative, Financial, Pedagogical) – configurable. |
| 3 | Syllabus coverage tracker | % coverage per sequence from syllabus + lesson data. |
| 3 | CBA gradebook | Know-how / Life-skills columns; optional CBA competency view for parents. |
| 3 | Inspection reports, ministry folder, event calendar, booklist, teacher credentials | As in main plan. |
| 4 | Badge system | Staff/student virtual badges; triggers (onboarding, milestone, delegation); QR; configurable types and criteria. |
| 4 | Physical ID cards | Print ID Card action; ReportLab/WeasyPrint; CR80; configurable front/back fields. |
| 4 | Parent medal case | Student badges in parent profile; achievement-based; evidence links. |
| 5 | Badge advanced | Optional: scan log, heat map, offline verification cache, teacher/student gamification. |
| 5 | Automation polish | Notify delegate (SMS/email); Summary Report on delegation end; deadline reminders for syllabi. |

---

## 9. Configurable, World-Class, No Hardcoding

- **Labels:** All user-facing strings (e.g. "Dean," "Acting Principal," "Covering," "While You Were Away") translatable and, where needed, overridable in Site Settings or admin.
- **Roles and hierarchy:** No hardcoded role names in business logic; use configurable lists (e.g. syllabus_approval_roles, delegation_role_mapping).
- **Criteria and thresholds:** Badge criteria (e.g. attendance > 95%, average ≥ 16/20) and delegation rules (max duration, who can delegate to whom) come from admin/DB.
- **Region-agnostic:** Cameroon-specific behaviour (e.g. CBA, blood group on ID) is achieved by **configuration** (templates, optional fields, schema), not by hardcoded "if country == Cameroon". Same codebase can serve other regions with different config.
