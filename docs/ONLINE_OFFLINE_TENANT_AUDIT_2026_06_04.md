# Online vs Offline Tenant-Operations Audit — 2026-06-04

Exhaustive, aggressive audit of the full tenant lifecycle across **online and offline**
modes: onboarding/provisioning, offboarding/erasure/purge, every person-signup path,
offline operational write coverage, WAL/sync integrity, and offline auth / tenant
isolation. Method: 5 parallel read-only domain audits, each assuming *nothing works
offline until proven*, with the top P0s re-verified against the actual code before any fix.

**Architecture recap (confirmed):** online-first SaaS + an offline **write-queue** for
tenant *operations* (PWA + service-worker + IndexedDB/Dexie + WAL stream `/ws/wal/` →
Redis Streams → Celery drain under `rls_school`). Signup/provisioning are **online-only by
nature** (DB/SMTP/IdP). `RMC_DEPLOYMENT_PROFILE = online|edge|hybrid`; `edge` = LAN
self-host. There are in fact **three uncoordinated offline rails**: (1) the WAL stream
(`rmc-wal-stream.js`, auto-drains), (2) the OfflineAction queue (`data-rmc-offline-form`,
drains on a "Process queue" action, has real conflict handling), (3) a generic HTTP replay.
The same logical write can land on different rails depending on which template fired.

---

## A. FIXED in this pass (WAL core — verified live bugs)

All in `apps/wal_stream/` + one offline-queue fix. `manage.py check` clean;
`apps.wal_stream.tests.test_v4_zero_latency` 32/32 green.

| ID | Fix | Was |
|----|-----|-----|
| **F1** | `grade` writer now sets `created_offline_at=timezone.now()` | `OfflineMarkEntry.created_offline_at` is NOT-NULL no-default; `bulk_create` bypasses defaults → **every offline grade raised `IntegrityError`** which the drain did NOT catch → entry never `xdel`'d → **head-of-line poison pill wedging the entire tenant's drain forever**. `grade` is appended live by `rmc-gradebook-wal-enhance.js`. |
| **F2** | Drain loop now catches `DatabaseError` + has a **bounded retry → dead-letter** (`_MAX_APPLY_ATTEMPTS=5`, `rmc.wal.attempts.*` counter, `rmc.wal.deadletter.*` stream) | `IntegrityError`/`DatabaseError` propagated out of the loop and wedged the tenant; `unknown_tenant_hash` (deleted tenant) was caught but `continue`d without `xdel` → re-processed every drain cycle forever. Now any permanently-failing envelope parks after 5 tries. |
| **F3** | **Removed** the `billing_charge` WAL domain (writer + registry + consumer allow-list) | Writer built `Invoice(amount=, currency=, memo=)` — **fields that don't exist** (real: `total_amount`/`notes`) and omitted the required PROTECT `profile` FK → `TypeError` on every call, **swallowed**, money write **silently lost after the idempotency key was already burned**. Had **no client producer**. Offline finance correctly uses the proven OfflineAction finance handlers. A real billing WAL domain must be rebuilt against the actual `Invoice` contract **with DB tests**. |
| **F4** | `attendance` + (note) `teacher_attendance` writers: stamp `school_id=envelope["school_id"]` | `bulk_create` bypassed `Attendance.save()`'s school inference → attendance rows landed `school=NULL` (RLS/reporting gap). (`TeacherAttendance` has no `school` column — scoped via the teacher FK; left as-is with a note.) |
| **F5** | Offline `field_capture` with a **structured-but-unhandled** workflow now preserves the data as a note **and** returns `ok:False` → row marked **FAILED** (visible in the sync review queue) | Unknown structured workflows (e.g. `people_student_create`, POS sale, erasure) silently fell through to a `StudentNote` and were marked **SYNCED** — the UI said "saved", the structured operation was discarded, and nothing surfaced. Silent data loss. |

Also fixed earlier today (same offline thread): the WAL envelope never carried
`school_id` (drainer resolved it but didn't stamp it) → offline **messages** landed
`school=NULL`; `_apply_envelope` now stamps `envelope["school_id"]` for all writers.

---

## B. Full findings by domain (OPEN unless marked FIXED)

Severity: **P0** data-loss/security/money · **P1** broken core flow · **P2** degraded · **P3** polish.
Locus: **INT** = fixable in-repo · **EXT** = needs SMTP relay / payment provider / infra / Redis config.

### 1. Tenant onboarding / provisioning
- The memory'd `NameError` in `_do_provision_tracked` sync fallback is **VERIFIED FIXED** (imports re-declared `apps/schools/tasks.py:507-511`).
- **P1/INT** `/api/trial/` (`signup_views.py:1346`) creates a **live ACTIVE tenant with no email-ownership verification** and **no rate limit** — anyone can spin up tenants under emails they don't own.
- **P1/INT** `signup_school` + `api_trial_school` have **no rate limiting** → unbounded inactive-tenant rows + verification-email spam (reputation risk).
- **P1/INT(+EXT)** Sync provisioning fallback runs the **entire** pipeline (schema, DNS, seeding, welcome email) **inside the `verify_signup` HTTP request** → exceeds the 30s gateway timeout on Render free tier → half-provisioned tenant. Needs off-request provisioning (and/or a real worker).
- **P1/EXT+INT** Verification & welcome emails: default async daemon-thread does not durably deliver without an SMTP relay; a failed welcome email + `set_unusable_password()` can **lock out the first admin**; setup URL falls back to `localhost` when `MULTI_TENANT_BASE_DOMAIN` is unset.
- **P2/INT** Slug/subdomain create-race → uncaught `IntegrityError` → 500 instead of "URL taken".
- **P2/EXT** No DNS automation by default → fresh tenant subdomain may not resolve (only a SKIPPED audit event).
- **P3/INT** Signup page not offline-aware (generic `/offline/`); edge first-onboarding undocumented. (Provisioning offline is correctly N/A by design.)

### 2. Tenant offboarding / erasure / purge
- **P0/INT** **Hard purge leaves orphaned PII.** Purge only walks Django `ForeignKey`s to `School`; **13 bare `school_id`/`tenant_id` (non-FK) columns across 6 models survive** — incl. `AIEmbeddingStore` (embeddings of tenant content), `events.DomainEvent`/webhooks, `platform_runtime` workflow/reactivation rows. `build_inventory` shares the blind spot, so the manifest **under-reports** → false "complete" assurance.
- **P0/INT** **WAL Redis stream is outside the purge boundary** — `rmc.wal.<hash>` + `rmc.wal.dedupe.<hash>` (unsynced attendance/grades/messages) **persist in Redis after "permanent" deletion**. (F2 now at least stops the deleted-tenant poison-pill from looping forever, but the keys still aren't deleted on purge.)
- **P0/INT** **Right-to-be-forgotten requests vanish.** The non-staff erasure web form only writes a `ComplianceAuditLog` row — it **never creates an `EraseRequest`**, so the full fulfillment + SLA pipeline that exists is **never fed**. (Erasure is also anonymization-only, not deletion — acceptable with retention duties but should be explicit.)
- **P0/INT+EXT** **No subscription cancellation** on any offboard/purge path; `TenantSubscription` is CASCADE-deleted locally → **dangling Stripe subscription keeps billing with no local trace**; no final invoice.
- **P1/INT** `deactivate` doesn't suspend the subscription or flush live sessions; offline writers ignore wind-down mode.
- **P1/INT** `on_delete=SET_NULL` School FKs (e.g. `billing.source_school`) orphan to NULL rather than delete.
- **P1/INT** DSAR export runs **synchronously in the request** (times out for large tenants); partial-export failures are swallowed but success is still reported.
- **P2/INT(+EXT)** `notify_purge_completed` never emails the tenant; all offboarding mail is `fail_silently=True`.

### 3. Person signup (teacher / student / parent / admissions / bulk)
- **P0/INT** *(FIXED surfacing via F5)* Offline student/applicant create silently became a note marked SYNCED → **silent data loss + misleading success toast**. F5 now surfaces it as FAILED + preserves the data; the real fix is a person-creation offline path (G4) or an explicit "online-only" block.
- **P1/INT** **Guardian-invite admin action delivers the claim token through *no channel*** (`people/admin.py:392`) → guardian portal onboarding is undeliverable unless tokens are hand-carried.
- **P1/INT** Parent account created via the student form gets `set_unusable_password()` + **no set-password link**; the (off-by-default) welcome email contains **no login link** → unusable account.
- **P1/INT** **No person-creation WAL domain** → at an offline edge/LAN school, a teacher/student/parent **cannot be onboarded at all** (the single biggest hole in the offline-first promise).
- **P2/INT** Teacher create (`backend_teacher_create`) sends **no** invite/activation email; password shown in a flash message. Should route through the well-built `TenantStaffInvite` flow (the best email path in the codebase — idempotent + link-fallback when SMTP fails).
- **P2/INT** Bulk CSV import creates students only; **guardians stored as dead JSON**, no accounts/links/emails.
- **P2/INT** Admissions conversion creates an **orphan StudentProfile** (no User, no parent, no class, no enrollment email).
- **P2/INT(+EXT)** Applicant decision email silent-fails on empty SMTP with no operator-visible fallback.
- **P2/INT** No student User/login provisioning exists anywhere.
- **P2/EXT+INT** All recipient emails silently no-op when prod SMTP creds are empty; only the staff-invite path surfaces a fallback link.

### 4. Offline operational write coverage + WAL integrity
- **P0/INT** *(FIXED F3)* `billing_charge` writer broken — silent financial loss.
- **P0/INT** *(FIXED F1/F2)* `grade` writer `IntegrityError` poison-pill.
- **P1/INT** *(FIXED F5)* unhandled `field_capture` workflows marked SYNCED.
- **Coverage holes (P1/P2, INT):** **discipline/incidents, health/clinic, library, transport, hostel, cafeteria/meals, timetable, report cards, consents have *no* offline handling** — a plain POST while offline just errors, nothing queued. Several `notes_report` surfaces (waiver request, POS sale) lose the real operation.
- **P1/INT** 24h dedupe window < a plausible offline span (multi-day outage) → replays re-apply on non-idempotent writers (`grade` had no unique constraint; `announcement_create` would duplicate).
- **P1/INT** `vector_clock` is **decorative** — no writer reads it; apply order is Redis arrival order, not clock order → a **stale offline write can clobber a newer online write** with no conflict detection (the OfflineAction rail *does* detect conflicts; WAL does not).
- **P1/INT** Over-cap (>256 KiB) batch is rejected but the client **re-ships it forever** (no chunking).
- **P1/INT** No DLQ/retry-cap on the *client* outbox; *(F2 added one server-side.)*
- **P2/INT** Client outbox is **unbounded** — acked rows never deleted, undecryptable rows never evicted → IndexedDB growth → browser quota eviction could drop *queued* rows.
- **P2/INT** Client `tenant_hash` derived from `window.location.host`, not `school_id` (latent; server overwrites it so it works by luck).
- **P1/INT (architecture)** Three uncoordinated offline rails with divergent dedupe windows, conflict policy, and drain triggers — the safer rail (OfflineAction, has conflict detection) and the auto-draining rail (WAL, had the P0 writer bugs) can both receive the same logical write.

### 5. Offline auth / service-worker / tenant isolation
- **P0/INT** **`OfflineCapabilityToken` is never verified or revoked anywhere** — it's a write-only model. The WAL WS authenticates purely from the **session cookie**; `is_valid`/`expires_at`/`revoked_at`/`permission_bitmap` are **dead** (only referenced in tests). So offboarding/expiry/revocation **do not stop offline writes**. Either wire token verification + a revocation hook into the WS/writers, or stop advertising scoped/revocable offline auth (it's currently a false guarantee).
- **P0/INT** WAL writers **trust client-supplied FK IDs with no tenant validation** beyond RLS-on-FK. Highest risk: a forged `counterparty_id`/`student_id` from another tenant — under django-tenants schema mode `rls_school()` is a **no-op**, so the writer is the only line of defense and currently provides none. (F3 removed the billing writer; attendance/grade still trust `student_id`/`classroom_id`/`subject_assignment_id`.) **Fix:** each writer should validate every client FK belongs to `envelope["school_id"]` before insert.
- **P1/INT** `offline_capability_bitmap` **defaults to `["attendance.mark","grade.submit"]` for users with zero caps** — latent privilege grant the moment the bitmap is enforced.
- **P1/INT** Service-worker `DYNAMIC_CACHE` is **not purged on logout** → on a shared device (kiosk/staff laptop) user B can be served user A's cached `/api/...` PII.
- **P2/INT** `_resolve_school_id_from_hash` walks **all** schools under `rls_bypass` per drain (O(N) + dangerous context); `sha256[:12]` = 48-bit truncation (collision risk at scale). Fix: store `tenant_hash` as an indexed `School` column.
- **P2/INT+EXT** Redis WAL stream stores **plaintext PII** (the client outbox has opt-in AES-GCM; the server stream does not).
- **P2/INT** No enforced offline session ceiling (decoupled from token expiry, which is unenforced anyway).
- **P2/INT** Navigations are cache-first → stale shell HTML after a deploy (use network-first for `mode==="navigate"`).
- **P3** WS tenant binding trusts `X-Forwarded-Host` (defense-in-depth only; membership check still gates).

**Correctly hardened (no action):** WS `tenant_hash`/`user_id` + drain-time `school_id` are all server-derived (forgery blocked); `_apply_announcement_create` re-derives publish/approval authority server-side; grade `teacher_id` resolved from the socket; WAL WS correctly not booted on control-plane.

---

## C. Consolidated remediation roadmap

**Done this pass:** F1–F5 + the earlier `school_id` envelope stamp.

**Next P0 tranche (all INTERNAL):**
1. WAL writer tenant-FK validation (attendance/grade) — validate `student_id`/`classroom_id`/`subject_assignment_id` belong to `envelope["school_id"]`.
2. Decide `OfflineCapabilityToken`: wire verification + revocation hook **or** remove the false guarantee.
3. Erasure form → create `EraseRequest` (feeds the existing SLA/fulfillment pipeline).
4. Purge completeness: sweep bare `school_id`/`tenant_id` columns + count them in the manifest; `DEL` the tenant's `rmc.wal.*` Redis keys on purge.
5. Subscription cancellation on offboard (INT call; EXT = Stripe) before the CASCADE deletes the local row.

**P1 tranche (INTERNAL):** SW `DYNAMIC_CACHE` purge on logout; `offline_capability_bitmap` permissive-default removal; guardian-invite + parent set-password link delivery; route teacher-create through `TenantStaffInvite`; signup/`api_trial` verification + rate-limit; WAL dedupe window vs offline span (+ per-domain idempotency / unique constraints); vector_clock conflict resolution (or route WAL through the OfflineAction conflict resolver); off-request provisioning; offline coverage for discipline/health/library/transport/etc.; a **person-creation WAL domain** for edge onboarding.

**P2/P3 (INTERNAL):** indexed `School.tenant_hash`; client outbox eviction + batch chunking; DSAR export as a task; navigations network-first; deactivate→session flush.

**EXTERNAL (fix later, per your note):** SMTP relay + SPF/DKIM (the whole email-delivery class); a real Celery worker / paid tier; Stripe API for cancellation; DNS automation; Redis at-rest encryption.

---

## D. Testing posture / honest limitations
- The WAL-core fixes were validated by `apps.wal_stream.tests.test_v4_zero_latency` (32/32, SimpleTestCase) + `manage.py check`.
- **DB-backed `TestCase` modules cannot run in this Windows sandbox** (test-DB creation hangs/locks); the offline-queue + provisioning + compliance tests must run in CI/Linux. Static analysis (AST parse, import, `manage.py check`, `makemigrations --check`) was used where DB tests couldn't run.
- Findings above are code-verified; the top P0s were re-read against source before fixing (two subagent claims were corrected during fixing: `TeacherAttendance` has no `school` column; a latent `created.append` NameError from an earlier edit).
