# Gilead Technical High School – Staff, Org Tree, ID & Deactivation Plan

Single implementation plan for **Gilead Technical High School** (GileadTech), Cameroon, private vocational school. Covers staff profiles, organizational tree, photo/ID lifecycle, deactivation protocol, and **Scanned Denied** gate UI.

---

## 1. Staff profile fields (GileadTech + Cameroon)

**Single source of truth** for HR and academic planning.

| Area | Fields |
|------|--------|
| **Identification** | Full name, Employee ID (GTHS…), profile photo, job title (e.g. "Senior Mathematics Teacher", "Workshop Lead – Welding") |
| **Contact** | School email, phone extension, preferred contact hours |
| **Academic** | Subjects taught, grade levels, classroom/workshop URL (Meet/Zoom) |
| **Admin** | Direct supervisor, Department (STEM, Humanities, or one of 8 technical departments), Home school (if multi‑campus) |
| **Credentials** | Certifications, years of experience, specialized skills |
| **Cameroon** | **Matricule** (gov’t ID for civil servants / school ID for private), **Administrative rank** (e.g. PLEGG, PLEG, PAET or “Private”), **Pedagogic department** (English, French, Sciences, etc.), **Documentation status** (Integration File / professional authorization) |
| **GileadTech** | **Technical specialty** (Accounting, Electrical Power Systems, Building Construction, Plumbing, Fashion Design, Motor Mechanics, Carpentry, Welding), **Workshop lead** (yes/no + facility), **Bilingual** (EN/FR), **Technical certification status** (MINESEC vocational) |

**Implementation:** Extend `TeacherProfile` (or equivalent staff model) with the above; ensure Matricule and technical specialty are first‑class. Add optional “staff type” (teaching vs support) for org tree.

---

## 2. Organizational tree structure

**Hierarchy (GileadTech):**

- **Level 1 – Governance:** Proprietor / Board → **Principal**
- **Level 2 – Admin core:** **Vice Principal (Academic / Censor)**, **Bursar**, **Senior Discipline Master (SDM)**
- **Level 3 – Departments:** HODs for 8 technical specialties + Support (IT, Library)
- **Level 4 – Instructional & support:** Specialty teachers, general education teachers, form masters/mistresses, workshop technicians

**Linking:** Primary reporting = solid line (e.g. Teacher → Principal); secondary/functional = dotted (e.g. Teacher → cross‑functional lead). Each node links to the person’s **full profile**.

**Views:**  
- Full tree (all levels).  
- **Departmental view:** e.g. “Electrical Power Systems” shows HOD + all staff/students for that workshop.

**UX:** Grouped boxes for same role (e.g. “Form 5 teachers”), expandable. **Text/search directory** alongside the graphical tree (accessibility). **Bilingual labels** (EN/FR): Principal/Proviseur, Censor/Censeur, Bursar, SDM/Discipline Master, etc.

**Data:** Tree driven from DB (staff + reporting relationships). Span of control ~12:1–15:1 (staff to admin roles).

---

## 3. Photo capture & ID lifecycle

**Onboarding (gatekeeper step):**  
After personal details, before final submit: **“Biometric & ID capture”** step.

- **Capture:** “Capture now” → `getUserMedia()` (webcam/tablet); live preview + face overlay; crop to ID ratio (e.g. 2×2 in or 300×300 px).
- **Storage:** Cloud (e.g. S3) or configured storage; link to user’s **Matricule / unique ID**; consent checkbox for use on school ID.
- **Lifecycle:**

| Status | Profile | ID/Badge | System access |
|--------|--------|----------|----------------|
| **Active** | Photo on dashboard | Valid, scannable | Full |
| **Suspended** | Flagged “Pending” | Temporarily invalid | Denied at gate/portal |
| **Deactivated** | Archived/watermarked “INACTIVE”/“VOID” | Voided | Account locked |

**Kill switch:** When status → **Deactivated**, immediately: invalidate QR/barcode (blacklist), lock portal, watermark/archive photo; gate scan returns **Denied**.

**Extras (GileadTech):** Use photo for workshop pass (safety clearance), bilingual PDF ID (EN/FR), and visual attendance in workshops.

---

## 4. User offboarding & deactivation protocol

**Triggers:**  
Graduated | Resigned/Terminated | Withdrawn/Expelled → set status to **Inactive/Deactivated**.

**Automated (“digital kill‑switch”):**  
- Revoke portal access; kill sessions.  
- Move ID to **blacklist**; gate/workshop scans → Access Denied.  
- Remove from workshop/resource groups.

**Archiving (MINESEC / local):**  
- Do not delete: watermark photo, retain learning/service history for transcripts.  
- Hide from active directory; ID card image → “Card Expired” on app.

**Clearance form (before final “Deactivate”):**  
- Workshop tools returned (signed by Technical HOD).  
- Physical badge collected (for shredding).  
- Bursar: fees/books cleared.

**Notifications (Email + SMS/WhatsApp):**  
- **Principal / SDM:** “Security Alert: Access Revoked for [Name] (ID: [Matricule]). Digital access blocked; ID void. Recover keys/equipment.”  
- **Bursar:** “Final clearance: [Name] – verify fees and tool deposits; profile locked.”  
- **User:** “Account and ID deactivated; return physical card to Admin.”

**Audit:** Log every notification and deactivation step.

---

## 5. Scanned Denied (gate UI + notify Discipline Master)

When a **deactivated** (or invalid) ID is scanned at the gate:

**Screen (mobile‑first):**  
- Large **ACCESS DENIED** / **ID CARD INVALID**.  
- User info: **Name**, **ID** (e.g. GTHS00790), **STATUS: DEACTIVATED**, small profile photo.  
- Button: **“HOLD CARD & NOTIFY DISCIPLINE MASTER”**.

**Action:**  
- Button triggers **push/instant alert to Discipline Master**: e.g. “Alert: Deactivated ID [ID Number] scanned at Main Gate.”  
- Optionally log scan event (time, gate, device) for audit.

**Implementation:**  
- **Backend:** Gate/scan API that accepts scan payload (ID/QR), checks blacklist + status; returns `denied` + profile summary (name, id, status, photo URL) and records scan.  
- **Frontend:** Dedicated “gate scan result” page (or in‑app view) used by security device; show the denied UI and “Notify Discipline Master” button that calls an API to send the alert (and optionally open WhatsApp/sms link).  
- **Place in codebase:** e.g. `apps/gate` or `apps/access` (scan validation + alerts); portal or standalone gate UI template that matches the described screen.

---

## 6. Implementation phases (summary)

| Phase | Scope |
|-------|--------|
| **1 – Data & profile** | Staff profile fields (Cameroon + GileadTech); Matricule, technical specialty, workshop lead, bilingual, certifications; reporting relationships for org tree. |
| **2 – Org tree** | Hierarchy (Proprietor → Principal → Censor, Bursar, SDM → HODs → staff); solid/dotted links; departmental view; bilingual labels; text directory. |
| **3 – Photo & ID** | Onboarding photo step (camera, crop, consent); storage; ID lifecycle (Active/Suspended/Deactivated); kill switch + blacklist. |
| **4 – Deactivation** | Clearance form; notifications (Principal, Bursar, user); audit log. |
| **5 – Scanned Denied** | Gate scan API (blacklist + profile); “Scanned Denied” UI; “HOLD CARD & NOTIFY DISCIPLINE MASTER” → alert to Discipline Master. |

**Tech notes:**  
- Mobile‑first, low‑bandwidth friendly; EN/FR toggle.  
- 8 technical departments: Accounting, Electrical Power Systems, Building Construction, Plumbing, Fashion Design, Motor Mechanics, Carpentry, Welding.

---

## 7. Scanned Denied UI reference

- **Layout:** Red/white “ACCESS DENIED” and “ID CARD INVALID”; white card with name, ID (GTHS…), STATUS: DEACTIVATED, photo; red button “HOLD CARD & NOTIFY DISCIPLINE MASTER”.  
- **Asset:** See `assets/.../image-33c5313e-67e7-442c-8fa2-ba02e4da1a5a.png` for visual reference.

This plan is the single reference for implementing staff profiles, org tree, ID lifecycle, deactivation, and Scanned Denied at Gilead Technical High School.
