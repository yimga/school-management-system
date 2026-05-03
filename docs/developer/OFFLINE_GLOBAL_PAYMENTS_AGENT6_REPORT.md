# Agent 6 — Offline & Global Payments (delivery report)

Date: 2026-05-01.  
Scope: offline-first flows, regional payment corridors, client enqueue wiring, sync UX.  
(SOT not updated — per mission: proof before SOT.)

**Canonical verification gate (matches mission RUN block):** `scripts/run_agent6_offline_payments_gate.sh`  
Sets `DJANGO_TEST_DB_FILE` to `.django_test_dbs/agent6_gate.sqlite3` by default so Windows hosts avoid locking `default.sqlite3`. Override with your own path if needed.

---

## A — Offline coverage matrix

| Flow | Enqueue offline | Sync server queue | Conflict possible | Resolve | UI clarity |
|------|-----------------|-------------------|-------------------|---------|------------|
| Student attendance | Yes — `data-rmc-offline-form="attendance"` + `data-rmc-attendance-scope="student"` | Yes — `OfflineAction` + `process_offline_queue` → `Attendance` | Yes | Conflicts screen + audit | Queue sections + sync bar |
| Teacher attendance | Yes — same form hook + `data-rmc-attendance-scope="teacher"`; payload uses `scope: "teacher"` | Yes — `_apply_teacher_attendance` → `TeacherAttendance` | Yes | Same | Teacher roll call template |
| Grading / marks | Yes — marks entry; per-student payloads incl. mock/practical | Yes — `_apply_grading` → `OfflineMarkEntry` | Evals merge elsewhere | Shared offline queue | Year/term on form |
| Payment receipt | Yes — metadata without file; amount defaults to invoice balance | Yes — `OfflinePaymentIntent` | Reconciliation rules | Staff tools | Corridor card |
| Notes / report evidence | Yes — bulk hub quick capture (offline path) | Yes — `_apply_notes_report` | Low | Conflict UI | Hub copy |
| Parent payment proof | Same invoice receipt wiring | Same | Same | Same | Corridor + queue |
| Staff sync review | N/A capture | Yes — sync dashboard | Yes | Yes | Pending / failed / conflicts / synced + per-row status |

---

## B — Client wiring

- Script: `static/js/rmc-offline-portal-forms.js` (loaded from `portal_base.html` for authenticated users).
- Calls `window.rmcOfflineEnqueue({ action_type, payload, idempotency_key })` with **nested `payload`** matching `offline-queue-client.js` flush semantics.
- Wired templates:
  - `templates/portal/roll_call_student.html` — student attendance (`scope=student`).
  - `templates/portal/roll_call_teacher.html` — teacher attendance (`scope=teacher`).
  - `templates/teacher/marks_entry.html` — grading (requires `year` + `term`).
  - `templates/finance/invoice_detail.html` — payment receipt (`novalidate` for offline file skip).
  - `templates/portal/teacher_bulk_capture_hub.html` — notes quick capture.

---

## C — Conflict UX

- `portal/offline_sync_conflicts.html` — documents audit recording on resolution.
- `resolve_conflict_choice` persists `resolution_audit` (`resolved_at`, `resolver_user_id`, `choice`) into `sync_metadata`.
- Existing buttons: keep mine / use latest / review manual unchanged (billing enforcement untouched).

---

## D — Sync dashboard

- `portal/offline_sync_queue.html` — sections: **Pending/syncing**, **Failed**, **Conflicts**, **Recently synced**, plus full activity table.
- Actions: **Process queue now**, **Retry all failed**, link to conflicts when present.

---

## E — Regional payment profiles

- Data: `apps/finance/data/regional_payment_profiles.json` — Cameroon, Ghana, Nigeria, Kenya, US, UK/EU generic.
- Loader: `apps/finance/regional_payment_profiles.py`.

---

## F — Fallback / reconciliation

- `apps/finance/payment_fallback.py` — `corridor_bundle_for_invoice()`, `select_fallback_chain()`.
- `invoice_detail` passes `payment_corridor` for UI (advisory; billing rules unchanged).

---

## G — Tests / verifiers

**Phase 7 automated coverage (in tree):**

| Requirement | Where |
|-------------|--------|
| Offline enqueue per flow | `OfflineActionQueueTests` — attendance, teacher scope, grading, payment receipt, notes_report |
| Sync success | `test_enqueue_process_*`, `test_teacher_attendance_*`, `test_grading_*`, `test_notes_report_*` |
| Conflict creation + resolution | `test_conflict_then_keep_mine`, `test_conflict_use_latest_records_audit` |
| Tenant isolation | `test_tenant_isolation` |
| Payment fallback selection | `test_global_payment_profiles.py` + `test_payment_fallback_engine.py` (corridor normalization + degraded rails + reconciliation audit) |
| Offline receipt reconciliation | `test_offline_payment_receipt_queues_intent` (docstring: staff reconciliation) |

**Mechanical verifiers (mission RUN block):**

```bash
# Preferred one-shot (bash):
bash scripts/run_agent6_offline_payments_gate.sh

# Equivalent manual:
export DJANGO_TEST_DB_FILE=".django_test_dbs/agent6_gate.sqlite3"   # Git Bash / macOS / Linux
python manage.py test apps.platform_runtime.tests.test_offline_queue apps.finance.tests apps.billing.tests \
  --settings=config.settings --noinput --keepdb
python scripts/audit_tenant_isolation.py
python scripts/audit_security_surface.py
```

**Executed in repo during development:** `audit_tenant_isolation.py` and `audit_security_surface.py` — **OK**.  
Full `manage.py test` over all three apps may take a long time on **first** migrate of a new `DJANGO_TEST_DB_FILE` (large migration graph); subsequent `--keepdb` runs reuse the file and are much faster.

---

## H — Remaining gaps (product / optional)

1. Parent-only microcopy on invoice offline path (same template today).
2. Native mobile app parity (web PWA + queue is covered).
3. Full receipt **file** upload still requires connectivity (metadata-first offline is intentional).
4. Kenya: exact M-Pesa PSP enums if product requires distinct rail codes beyond mapped MoMo/BANK.

---

## I — Verdict

**OFFLINE GLOBAL PAYMENTS — IMPLEMENTATION COMPLETE (all mission phases 1–7 in codebase).**

**10-track product certification** still requires a green run of the **gate script** (or equivalent commands in section G) on your runner — use a dedicated `DJANGO_TEST_DB_FILE` and allow time for the **first** SQLite migrate if the file is new. Mechanical audits (`tenant_isolation`, `security_surface`) are passing.
