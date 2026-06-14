# Data Subject Access Request (DSAR) — Runbook

**DRAFT — pending counsel review.** This runbook is operator-facing
scaffolding for the procedure RunMyCampus operators follow when a
Customer (acting as data controller) forwards a Data Subject Access
Request. It is NOT counsel-finalized; do not publish to customers
without legal review.

**Audience:** RunMyCampus operator / security operator handling DSAR
intake for a tenant.

**Last updated:** v3.33.0, 2026-05-18.

---

## 1. Statutory Window

| Jurisdiction | Statutory window | Source |
|---|---|---|
| GDPR (EU/EEA) | **30 calendar days** from receipt | Art. 12(3) |
| GDPR (extension) | +60 days when justified | Art. 12(3) |
| CCPA / CPRA (California) | 45 calendar days | Cal. Civ. Code § 1798.130(a)(2) |
| NY Ed Law § 2-d | "Without unreasonable delay" | § 2-d(4)(b) |
| UK GDPR | 30 calendar days | DPA 2018 |

**Internal target:** RunMyCampus delivers the technical export /
redaction / deletion to the controller within **7 business days** of
the controller's instruction, regardless of jurisdiction. This keeps
the controller well inside the statutory window with margin to handle
clarification or appeal.

---

## 2. Right Types In Scope

| Right | GDPR Art. | Action |
|---|---|---|
| Right of access | 15 | Export subject's Personal Data in machine-readable format |
| Right to rectification | 16 | Update fields under controller direction |
| Right to erasure ("right to be forgotten") | 17 | Delete or anonymize per retention policy |
| Right to restriction | 18 | Flag rows so processing pauses |
| Right to portability | 20 | Same as access but in a portable, structured format |
| Right to object | 21 | Stop automated processing the subject objects to |
| Right not to be subject to automated decision-making | 22 | Disable AI-driven decisions for that subject |

---

## 3. Intake Flow

```
Subject  →  Customer (controller)  →  RunMyCampus operator (processor)
```

The data subject sends the request to the **controller**, not to
RunMyCampus directly. If a request comes in via RunMyCampus support,
the operator:

1. Confirms the requester's identity is not verifiable by RunMyCampus
   alone (we don't know who the data subject is — the controller does).
2. Forwards the request to the controller's published DPO / privacy
   contact within **24 hours**.
3. Logs the forward in the ticketing system with no Personal Data in
   the ticket body.

---

## 4. Scope Clarification

Before processing, the controller must clarify:

1. **Subject identification.** Which row(s) in the tenant correspond
   to the data subject? Typically `StudentProfile`, `GuardianProfile`,
   `StaffProfile`, or `User`.
2. **Right type.** Access vs. erasure vs. rectification, etc.
3. **Scope of data.** All data? Specific domains? Specific time range?
4. **Format.** JSON, CSV, PDF — the controller's preference.
5. **Delivery channel.** Secure download link, email (encrypted),
   physical mail, etc.

The operator captures the clarification on the ticket and proceeds
only after the controller has signed off in writing.

---

## 5. Redaction Policy

When exporting under right-of-access (Art. 15), the export MUST NOT
include third-party Personal Data the data subject is not entitled to
see. Apply the platform's field-level DLP layer:

| Sensitivity tier | Action |
|---|---|
| `public` | include as-is |
| `internal` | include as-is |
| `restricted` | include — subject is entitled to see their own restricted data |
| `confidential` | include only after controller confirms the subject is entitled (e.g. health records — controller's HIPAA / FERPA assessment) |
| `secret` | redact unless the controller explicitly authorizes |

Third-party fields (e.g. another student named in a disciplinary
note) are redacted via the DLP `mask` strategy (`xx***yy`) or
`hash` strategy (`sha256:...[:12]`) depending on the controller's
preference.

The DLP layer is invoked via:

```python
from apps.policies.dlp import redact_record

redacted = redact_record(
    record=raw_dict,
    entity="people.StudentProfile",
    subject=request.user,
    school=school,
)
```

**Automated since 2026-06-10:** `apps.compliance.gdpr_services.export_student_data_portability`
now routes every export section through `redact_record(..., action="export")`
automatically (keyed by the data subject), so classified third-party fields are
masked per the field catalog without an operator code step. It degrades safely —
sections whose entity has no classified fields pass through unchanged — and emits
one `apps.policies.pdp.PolicyDecisionLog` row per export (`action="dsar_access_export"`).
The operator's pre-delivery review (§7) remains the human backstop; classify more
fields in the catalog to widen masking.

Audit log: every DSAR export is logged with `operator_user_id`,
`subject_external_id` (NOT the subject's name in plaintext), and the
sha256 fingerprint of the exported payload.

---

## 6. Export Format

### 6.1 JSON (default for Art. 20 portability)
- One JSON file per domain (students.json, guardians.json, etc.).
- UTF-8, BOM-less, pretty-printed.
- Each row keyed by canonical model + canonical_pk.
- Money fields as decimal strings (per `scan_money_float` policy).
- Timestamps as ISO 8601 with timezone.

### 6.2 CSV (controller request)
- One CSV per domain.
- Headers match canonical ontology field names.
- UTF-8 with BOM (Windows Excel compatibility).
- Multi-line values quoted per RFC 4180.

### 6.3 Export bundle (subject convenience)
- The right-of-access export is produced as a JSON/CSV **ZIP bundle**, not a PDF:
  per-student data via `apps.compliance.gdpr_services.export_student_data_portability(school_id, student_id, format="json"|"csv")`,
  or the full tenant bundle via `apps.schools.tenant_offboarding.run_wind_down_export(school, full=True)`
  (writes `portability_export.zip`; locate the latest via `latest_export_zip_path(school)`).
- There is no automated PDF pipeline today; if a subject requests a PDF, render
  it manually from the bundle and attach the §8 attestation alongside.

---

## 7. Operator Steps (Right of Access)

```
[ ] Ticket received from controller. Scope clarified. Sign-off in writing.
[ ] Identify subject row(s) in tenant. Cross-reference legacy IDs via
    MigrationIdMapping if migrated from a foreign SIS.
[ ] Run apps.policies.dlp.redact_record per row to apply sensitivity
    tiers + redaction strategies.
[ ] Generate export in requested format (§6).
[ ] Compute sha256 of the export bundle for audit log.
[ ] Upload to short-lived signed-URL bucket (24-hour expiry).
[ ] Deliver the signed URL + attestation (§8) to the controller.
[ ] Log the delivery in apps.policies.pdp.PolicyDecisionLog with
    action='dsar_access_export' (no Personal Data in the log).
[ ] Mark ticket closed with internal SLA timestamps.
```

---

## 8. Attestation

Every export carries a one-page attestation:

```
RUNMYCAMPUS DATA SUBJECT EXPORT — ATTESTATION

This export was prepared by RunMyCampus, Inc. on
<INSERT DELIVERY DATE> at the direction of <CONTROLLER NAME>, the
data controller for the tenant <TENANT NAME>.

Export sha256: <INSERT 64-CHAR HEX>
Domains included: <COMMA-SEPARATED LIST>
Time range: <START> to <END>
Redaction strategy applied: <COMMA-SEPARATED LIST>

Operator: <INSERT OPERATOR NAME / ROLE>
Audit reference: <INSERT TICKET ID>
```

---

## 9. Operator Steps (Right of Erasure)

```
[ ] Confirm controller has assessed there is no legal obligation to
    retain (e.g. FERPA retention requirements; financial-records
    retention).
[ ] Confirm there is no overriding legitimate interest of RunMyCampus
    (e.g. billing dispute, fraud investigation).
[ ] If retention is required, controller informs subject + RunMyCampus
    flags the row as 'erasure-deferred' with the legal basis.
[ ] If erasure proceeds: log an EraseRequest, approve it, then fulfil it via
    `python manage.py process_erase_requests` (batch) — or call
    `apps.compliance.gdpr_services.gdpr_scrub_student(school_id, student_id,
    dry_run=False)` directly. This anonymizes the StudentProfile + linked User,
    guardians, attendance/incident/evaluation notes, and matching applicants.
    (Run with `dry_run=True` first to preview.)
[ ] Migration artifacts (raw bundle ciphertext, intake files) are
    deleted per the 90-day retention in the MAA (Section 6 of v2.0).
[ ] Confirm via re-run of the access export that the subject's data
    is no longer returned.
[ ] Log to PolicyDecisionLog with action='dsar_erasure' and the
    subject's pseudonymous reference (NOT name in plaintext).
```

---

## 10. Operator Steps (Right to Rectification / Restriction)

- **Rectification.** Controller provides the corrected value. Operator
  updates the field via the staff-only admin or a scripted UPDATE
  guarded by `# tenant-isolation-allow:` markers. The change is
  audit-logged.
- **Restriction.** Controller asks RunMyCampus to "freeze" processing
  on a subject's row pending appeal. Operator flips the subject's
  `processing_restricted=True` flag (where supported); downstream
  systems honor the flag.

---

## 11. Rejection / Escalation

A controller may instruct RunMyCampus to reject a DSAR. Common
grounds:

- Manifestly unfounded or excessive (Art. 12(5)).
- Conflicts with the rights of others (third-party data).
- Conflicts with legal obligations (retention).
- Identity not verifiable to the controller's standard.

When the controller rejects, operator:

1. Receives the rejection in writing from the controller (email is
   sufficient; ticket attachment required).
2. Records the rejection rationale on the ticket.
3. Does NOT communicate directly with the data subject — that is the
   controller's responsibility.

---

## 12. Audit & Reporting

Every DSAR action emits one structured log line via
`apps.policies.pdp.PolicyDecisionLog`:

```python
PolicyDecisionLog.objects.create(  # tenant-isolation-allow: dsar-runbook-audit-log
    school=tenant,
    subject_user_id=operator.id,
    action="dsar_access_export",
    resource_kind="people.StudentProfile",
    resource_pk="<INSERT SUBJECT_PK>",
    effect="allow",
    reason="controller-instruction-ticket-<INSERT TICKET ID>",
)
```

Quarterly: operator runs `python manage.py dsar_summary --quarter=<Q>`
and ships the aggregate count + average TTR (time-to-resolution) to
the controller as a compliance metric (no Personal Data in the
aggregate report).

---

## 13. Contacts

| Role | RunMyCampus contact |
|---|---|
| Data Protection Officer | _(insert DPO name + email)_ |
| Security operator on-call | _(insert security ops paging address)_ |
| Customer success owner | _(insert CS owner email)_ |

Controller DPO / privacy contact: _(provided at tenant onboarding)_.

---

## Appendix A — Quick Reference Card

```
DSAR received → forward to controller within 24h
Controller instructs → operator processes within 7 business days
Statutory window     → 30 days (GDPR) / 45 days (CCPA)
Right of access       → export + redact + attest + signed-URL deliver
Right of erasure      → assess legal obligation, then erase or defer
Right of restriction  → flip processing_restricted=True
Always log to PolicyDecisionLog (no Personal Data in the log line)
Never communicate directly with the data subject
```

---

*End of DSAR Runbook.*
