# Data Processing Addendum (DPA) — Template

**DRAFT — pending counsel review.** This template is operator-facing
scaffolding for the customer-controller / RunMyCampus-processor
arrangement under GDPR Art. 28 and NY Education Law § 2-d. It is NOT
counsel-finalized; do not present to a customer without legal review.

**Audience:** RunMyCampus operator / customer success owner attaching
this addendum to a Master Services Agreement (MSA).

**Last updated:** v3.33.0, 2026-05-18.

---

## 1. Parties

- **Controller / Educational Agency** ("Customer"): the school, school
  district, or educational institution identified on the MSA.
- **Processor** ("RunMyCampus"): RunMyCampus, Inc., a Delaware
  corporation.

For GDPR purposes, Customer is the data controller and RunMyCampus is
the data processor. For NY Education Law § 2-d purposes, Customer is
the "educational agency" and RunMyCampus is a "third-party
contractor".

---

## 2. Scope of Processing

RunMyCampus processes Personal Data only on the documented
instructions of Customer, including the following categories:

| Category | Examples |
|---|---|
| Student records | name, date of birth, grade level, enrollment status, attendance, grades, schedules |
| Guardian records | name, contact info, relationship to student |
| Staff records | name, role, employment data |
| Financial records | invoices, payments, fees, payroll (where the Customer enables payroll) |
| Operational records | events, communications, library, transport, hostel, cafeteria |

**Purposes**:
- Provide the school management platform (SaaS) as contracted.
- Run migration / data-import workflows the Customer initiates.
- Provide operator-visible diagnostics and incident response.

**RunMyCampus will not**:
- Use Customer data for product analytics, AI/ML model training,
  marketing, or any purpose outside the contracted Services.
- Sell or rent Personal Data.
- Share Personal Data outside the sub-processor list (Annex B)
  without Customer's written consent.

---

## 3. Customer Obligations (Controller)

- Customer is responsible for the lawful basis of processing
  (consent, legitimate interest, public task, etc.).
- Customer is responsible for providing privacy notices to data
  subjects (students, parents, staff) per applicable law.
- Customer assesses the categories of Personal Data to be processed
  and configures the platform's data minimization controls
  accordingly (per the DPA-aligned scope settings in `siteconfig`).
- Customer routes Data Subject Access Requests (DSARs) per the
  Runbook (`docs/DSAR_RUNBOOK.md`); RunMyCampus assists.

---

## 4. RunMyCampus Obligations (Processor)

### 4.1 Instructions
RunMyCampus processes Personal Data only on the documented
instructions of Customer, except where required by Union or Member
State law (in which case RunMyCampus informs Customer beforehand).

### 4.2 Confidentiality
Personnel with access to Personal Data are bound by written
confidentiality obligations.

### 4.3 Security (GDPR Art. 32)
RunMyCampus maintains technical and organizational measures including:

- Encryption at rest (Fernet wrap for sensitive columns; see
  `docs/SECURITY_KEYS.md`).
- Encryption in transit (TLS 1.2+ enforced platform-wide).
- Tenant-scoped row-level security (RLS) inside the database.
- Role-based access control (RBAC) with a Policy Decision Point
  (PDP); audit trail in `apps.policies.pdp.PolicyDecisionLog`.
- Field-level data-loss prevention (DLP) driven by
  `FieldCatalogEntry.sensitivity_tier`.
- Continuous integration gates: `scan_tenant_queryset_safety.py`,
  `scan_money_float.py`, `scan_pii_logging_smell.py`, plus the broader
  `scripts/architectural-boundaries.yml` set.

### 4.4 Sub-processors
RunMyCampus engages the sub-processors listed in Annex B. Customer
authorizes their use upon signing. RunMyCampus provides 30 days'
written notice before adding a sub-processor; Customer may object in
writing within 14 days.

### 4.5 Assistance with Data Subject Rights
RunMyCampus assists Customer (the controller) in fulfilling Data
Subject Rights requests per the DSAR Runbook
(`docs/DSAR_RUNBOOK.md`):

- Right of access (Art. 15)
- Right to rectification (Art. 16)
- Right to erasure (Art. 17)
- Right to restriction (Art. 18)
- Right to data portability (Art. 20)
- Right to object (Art. 21)

RunMyCampus delivers the technical export / redaction / deletion
within 7 business days of Customer's instruction, well inside the
30-day statutory window.

### 4.6 Breach Notification
RunMyCampus notifies Customer without undue delay (and in any event
within 72 hours) after becoming aware of a Personal Data breach. The
notification includes the categories and approximate number of data
subjects + records affected, likely consequences, and remediation
steps taken.

### 4.7 Data Protection Impact Assessment (DPIA)
RunMyCampus provides reasonable assistance to Customer in carrying
out DPIAs (Art. 35) and prior consultations with supervisory
authorities (Art. 36).

### 4.8 Return / Deletion at End of Service
Upon termination, RunMyCampus deletes or returns all Personal Data
within 90 days, unless Union or Member State law requires storage.
Customer chooses (a) full tenant export (canonical-form JSON + CSV)
or (b) certified deletion with audit log.

---

## 5. NY Ed Law § 2-d (where applicable)

Where Customer is a New York "educational agency", RunMyCampus also:

- Complies with the Parents Bill of Rights for Data Privacy and
  Security (Customer publishes the supplemental information document).
- Provides employees training on data privacy and security.
- Notifies the Chief Privacy Officer of any unauthorized release of
  Student Data within 7 calendar days.
- Maintains a Data Security and Privacy Plan (Annex A reference).
- Does not sell Student Data or use it for marketing.
- Does not disclose to any other party (other than sub-processors)
  without Customer authorization.

---

## 6. International Data Transfers

If Personal Data is transferred outside the EEA, RunMyCampus relies
on:

- Standard Contractual Clauses (SCCs) as adopted by the European
  Commission (Decision 2021/914 of 4 June 2021), incorporated by
  reference. The Customer is the "data exporter"; RunMyCampus is the
  "data importer".
- Supplementary measures per the EDPB Recommendations 01/2020.
- A Transfer Impact Assessment (TIA) is available upon request.

---

## 7. Audit Rights

Once per calendar year, Customer may, upon 30 days' written notice,
audit RunMyCampus's compliance with this DPA. The audit is conducted
under reasonable confidentiality terms and may be performed by an
independent third-party auditor mutually agreed upon. RunMyCampus
makes available the SOC 2 Type II report (when current) as a primary
substitute for on-site audits.

---

## 8. Term and Termination

This DPA is effective from the MSA effective date and remains in
force as long as RunMyCampus processes Personal Data on Customer's
behalf. Sections 4.6 (Breach), 4.8 (Return/Deletion), and 7 (Audit)
survive termination.

---

## Annex A — Data Security and Privacy Plan (Reference)

The technical and organizational measures (TOMs) implemented by
RunMyCampus are described in `docs/SECURITY.md` and
`docs/SECURITY_BASELINE_CI.md`. Highlights:

- SOC 2 Type II audit (annual; report available under NDA).
- ISO 27001 alignment (controls mapped in
  `docs/ARCHITECTURE_RUNTIME.md`).
- Least-privilege access; production access requires MFA + audit log.
- Continuous security scanning (`scripts/scan_*.py` family — see
  `CLAUDE.md` for the full table).
- Quarterly penetration tests.
- Disaster Recovery: 4-hour RTO, 1-hour RPO; quarterly drill log at
  `docs/generated/dr_drill_log.json`.

---

## Annex B — Sub-processors

(Operator MUST keep this list current. Format: name, role, location.)

| Sub-processor | Role | Location |
|---|---|---|
| _(insert sub-processor 1)_ | _(insert role)_ | _(insert location)_ |
| _(insert sub-processor 2)_ | _(insert role)_ | _(insert location)_ |
| _(insert sub-processor 3)_ | _(insert role)_ | _(insert location)_ |

A current and complete list is published at
`https://runmycampus.com/legal/subprocessors` and updated within
14 days of any change. Customer receives email notification of any
addition via the contact listed in §11.

---

## 9. Liability

The liability cap, indemnity provisions, and force majeure terms in
the MSA apply to this DPA. No DPA term is intended to derogate from
GDPR's liability allocation under Art. 82.

---

## 10. Governing Law

This DPA is governed by the laws of the State of Delaware, except
where the substantive provisions of the GDPR or NY Ed Law § 2-d
require otherwise.

---

## 11. Contacts

| Role | RunMyCampus contact |
|---|---|
| Data Protection Officer (DPO) | _(insert DPO name + email)_ |
| Security operator | _(insert security operator email)_ |
| Customer success owner | _(insert CS owner email)_ |

Customer DPO / security contact: _(provided at signing)_.

---

## Checklist — GDPR Art. 28 / NY Ed Law § 2-d coverage

- [x] Subject matter, duration, nature, purpose (§§ 1, 2)
- [x] Type of Personal Data + categories of data subjects (§ 2)
- [x] Controller obligations (§ 3)
- [x] Processor obligations — security (§ 4.3)
- [x] Sub-processor authorization (§ 4.4)
- [x] Assistance with DSARs (§ 4.5)
- [x] Breach notification (§ 4.6)
- [x] DPIA assistance (§ 4.7)
- [x] Return / deletion at end of service (§ 4.8)
- [x] Audit rights (§ 7)
- [x] International transfer mechanism (§ 6)
- [x] NY Ed Law § 2-d supplemental items (§ 5)

---

*End of DPA template.*
