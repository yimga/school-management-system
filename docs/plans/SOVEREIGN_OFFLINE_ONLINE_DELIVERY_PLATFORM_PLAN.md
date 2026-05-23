# Sovereign Offline–Online Delivery Platform (SODP) — execution plan

**Status:** **PLANNED — NOT YET STARTED** (plan + SOT reservation only; implementation delegated to build agent)
**Plan owner:** RunMyCampus platform team
**Created:** 2026-05-23
**Target SW range:** `sms-v3.65.0` → `sms-v3.70.x`
**Batch IDs:** **1405** (program reservation) → **1406–1412** (implementation waves A–G)
**Plan scope:** **REPO FIRST** — no live corridor rollout claim until Lane 2 evidence exists
**Handoff-ready for:** Claude Code, Codex, Cursor — this file is the single build contract; do not spawn parallel strategy docs

**Canonical cross-links (extend, do not replace):**

- [`docs/LOCAL_HUB_MODE.md`](../LOCAL_HUB_MODE.md) — online / edge / hybrid deployment profiles
- [`docs/OFFLINE_PLATFORM_AND_DATA_INTEGRITY.md`](../OFFLINE_PLATFORM_AND_DATA_INTEGRITY.md) — platform-wide offline strategy
- [`docs/OFFLINE_SYNC_WHEN_INTERNET_RETURNS.md`](../OFFLINE_SYNC_WHEN_INTERNET_RETURNS.md) — reconnect UX
- [`docs/OFFLINE_MODE_GAPS.md`](../OFFLINE_MODE_GAPS.md) — known SW/queue gaps (Wave A closes these)
- [`docs/EMAIL_DELIVERABILITY.md`](../EMAIL_DELIVERABILITY.md) — SPF/DKIM/DMARC operator runbook
- [`docs/OFFLINE_HELP_APPLIANCE.md`](../OFFLINE_HELP_APPLIANCE.md) — air-gapped help lane
- [`docs/OFFLINE_ENCRYPTION_AND_KEYS.md`](../OFFLINE_ENCRYPTION_AND_KEYS.md) — device encryption hooks

---

## 0 — Executive summary (read this first)

RunMyCampus already ships **80% of the right architecture** for African / low-connectivity schools:

| Layer | Already in repo | This plan adds |
|---|---|---|
| **PWA offline queue** | Dexie + service worker + `offline-queue-client.js` | Harden SW replay, extend API coverage, close gaps doc |
| **Server queue + conflicts** | `apps/platform_runtime/offline_queue.py`, `apps/sync_engine/conflict_resolver.py` | Unified action envelope + idempotency everywhere |
| **Email reliability** | `apps/schoolops/email_delivery.py` (`send_transactional`, Celery, PII-safe logs) | **Server-owned notification intents** — never client SMTP |
| **Edge / hub** | `LOCAL_HUB_MODE.md`, `install_local_hub.sh`, hybrid profile | mDNS hub discovery, polished operator packaging |
| **Thick client scaffold** | `companion-tauri/` (Rust + TS, signed release path) | **Field Client** wrapping portal teacher flows |
| **Mobile API** | `apps/api/mobile_api.py`, delta sync | Capacitor shell + same DRF contracts |

**What we explicitly REJECT** from generic “zero-server PouchDB mesh” blueprints (security / compliance reasons):

1. **Client `SEND_EMAIL` actions** — clients queue **notification intents** (`notify.parent.low_balance`); Django renders templates + sends via `send_transactional` / Anymail.
2. **`@csrf_exempt` sync endpoints** — all sync uses DRF + session/JWT + tenant derived from auth, never body `tenant_id`.
3. **Offline JWT parse without signature verify for authorization** — offline uses **scoped offline-capability tokens** minted online; role elevation requires online re-auth.
4. **Client-minted global tenant IDs for signup** — offline signup creates **provisional device-scoped workspace**; cloud reconciles on first sync with operator approval.
5. **PouchDB ↔ CouchDB replication on port 5984** — that *is* a server process; we use **Django hub on LAN** + **signed delta export** for mesh, not CouchDB.
6. **Raw `django.core.mail.send_mail` from sync loop** — always `schoolops.email_delivery.send_transactional` + Celery beat retry.
7. **Ping `https://onrender.com` for reachability** — use tenant `reachability_url` (`/health/` or hub origin) from `SMS_OFFLINE_CONFIG`.

**North star:** One codebase, three delivery surfaces (browser PWA, Tauri Field Client, Capacitor mobile), two connectivity profiles (Render cloud + optional LAN hub), **zero duplicate business logic**.

---

## 1 — Phase 0 audit (do NOT re-audit — inherit these findings)

### 1.1 Systems to REUSE (mandatory — no forks)

| System | Path | Contract |
|---|---|---|
| Offline server queue | `apps/platform_runtime/offline_queue.py` | `OfflineAction` lifecycle: queued → syncing → synced / failed / conflict |
| Conflict policies | `apps/sync_engine/conflict_resolver.py` | Per-entity LWW / server-authoritative / manual_review (grades = manual) |
| Client outbox | `static/js/offline-queue-client.js`, `static/js/offline-db.js` | POST `/portal/api/offline/enqueue/` → process on reconnect |
| Service worker | `static/js/service-worker.js` | Attendance API queue; extend paths per Wave A |
| Email delivery | `apps/schoolops/email_delivery.py` | `send_transactional`, `send_bulk`, `EmailDeliveryEvent`, recipient hashing |
| Email health UI | `/super/email/health/`, `verify_email_delivery_surface.py` | Operator SPF/DKIM/DMARC + delivery stats |
| Mobile / delta sync | `apps/api/mobile_api.py`, `apps/api/sync_delta_api.py` | Batch replay + idempotency keys |
| Offline bundle provision | `apps/platform_runtime/offline_mode_bundle.py` | Auto-apply on school provision |
| Deployment profiles | `services/ai_deployment_posture.py`, `RMC_DEPLOYMENT_PROFILE` | `online` / `edge` / `hybrid` |
| LAN hub docs + installer | `docs/LOCAL_HUB_MODE.md`, `scripts/install_local_hub.sh` | Edge packaging |
| Tauri scaffold | `companion-tauri/` | Signed desktop path; extend for Field Client |
| Argon2 passwords | `config/settings.py` `PASSWORD_HASHERS` | Cloud login only — **never** replicate password hashes to device |
| Help offline | `docs/OFFLINE_HELP_APPLIANCE.md`, KB panel `data-rmc-kb-ai-offline` | Cached KB when AI unreachable |

### 1.2 Gaps this program closes

From [`docs/OFFLINE_MODE_GAPS.md`](../OFFLINE_MODE_GAPS.md):

- SW stale Cookie/CSRF on replay → strip auth headers, use `credentials: 'include'`
- 4xx infinite retry → move to failed store + user notification
- Replay order → sort by `createdAt`
- Queue size cap → configurable max per device
- Entity/requests API versioning → `updated_at` + 409 conflict payloads
- Idempotency keys on critical writes
- E2E offline → queue → replay Playwright spec
- Form-draft-save beyond marks

From operator blueprint feedback:

- Dual-state delivery (instant online vs queued offline) — **server-side** for email
- Device discovery — **mDNS for hub**, not for CouchDB
- Mesh sync — **signed delta blobs** to designated mule device, not P2P CouchDB

### 1.3 Explicitly OUT of scope (honest deferrals)

- Partner app store publish (Apple/Google) — Wave E scaffolds Capacitor; store listing is Lane 2
- Full offline tenant self-signup without operator — provisional workspace only
- On-device LLM for teachers — school ops offline yes; AI needs hub/cloud per `AI_DEPLOYMENT_POSTURE.md`
- CouchDB / RxDB / WatermelonDB as second source of truth — Dexie mirror + server Postgres remain canonical
- Bluetooth mesh — Wi‑Fi LAN only in v1; BLE deferred
- Per-tenant SMTP credentials on client devices — platform operator configures Anymail/Resend on Render/hub

---

## 2 — Architecture

### 2.1 Layer diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         DELIVERY SURFACES (same Django UI + APIs)            │
├──────────────────┬──────────────────────┬───────────────────────────────────┤
│ Browser PWA      │ Tauri Field Client   │ Capacitor Mobile (Android v1)     │
│ portal_base SW   │ companion-tauri fork │ WebView + secure storage plugin   │
│ Dexie outbox     │ SQLite cache + SW    │ Same JS bundles as PWA            │
└────────┬─────────┴──────────┬───────────┴──────────────┬────────────────────┘
         │                    │                          │
         │    ┌───────────────┴──────────────────────────┘
         │    │  OFFLINE ACTION ENVELOPE (client)         │
         │    │  { id: UUID, action_type, payload,       │
         │    │    device_id, idempotency_key, ts }       │
         │    └───────────────┬──────────────────────────┘
         │                    │ HTTPS (when reachable)
         ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  CONNECTIVITY TARGET (one active origin per session)                         │
│  • online  → https://*.runmycampus.com (Render Pro)                          │
│  • edge    → http://hub.local:8000/ (LAN Django)                             │
│  • hybrid  → cloud primary; SW retries hub_base_url on cloud failure       │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  DJANGO CLOUD / HUB (single codebase)                                        │
│  DRF: /api/v1/mobile/sync/, /portal/api/offline/*, delta sync               │
│  offline_queue.apply_client_batch → domain handlers                          │
│  NOTIFICATION INTENTS → template render → send_transactional (Celery)        │
│  conflict_resolver → SyncConflict model → operator UI                        │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  POSTGRES (tenant-scoped) + EmailDeliveryEvent audit trail                   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Offline action envelope (canonical — all clients)

**Never** allow free-form `SEND_EMAIL` from client. Use typed intents:

```python
# apps/platform_runtime/offline_action_types.py (NEW — Wave A)
class OfflineActionType(TextChoices):
  ATTENDANCE_MARK = "attendance.mark"
  GRADE_SUBMIT = "grade.submit"
  STUDENT_NOTE = "student.note"
  PAYMENT_PROOF = "payment.proof_upload"
  SUPPORT_TICKET = "support.ticket"
  NOTIFY_PARENT = "notify.parent"          # server picks template + channel
  NOTIFY_STAFF = "notify.staff"
  PROVISIONAL_SIGNUP = "provision.signup"  # device-scoped only until reconciled
```

Client payload for `notify.parent`:

```json
{
  "template_key": "low_meal_balance",
  "recipient_user_id": "uuid",
  "context": { "student_id": "uuid", "locale": "fr" }
}
```

Server resolves recipient email from DB (never trusts client `to:`), renders template, calls `send_transactional`.

### 2.3 Dual-state delivery (online instant vs offline queued)

| Path | When | Behavior |
|---|---|---|
| **Instant** | `navigator.onLine` + reachability OK | POST intent → server sends email/SMS in-request or Celery immediate → return `delivery_id` |
| **Queued** | Offline or reachability fail | Client writes to Dexie/SQLite outbox → UI shows “Will deliver when connected” |
| **Replay** | Reconnect | Batch upload with idempotency keys → server skips duplicates via `OfflineAction.client_idempotency_key` unique constraint |

**UX copy (mandatory):** Never promise “email sent” offline — say **“Notification queued — delivers automatically when this device reconnects.”**

### 2.4 Offline authentication (security-first)

| Pattern | Verdict |
|---|---|
| Store Argon2 password hashes on device | **FORBIDDEN** |
| 90-day JWT + offline parse for admin role | **FORBIDDEN** for authorization |
| Online login → mint **OfflineCapabilityToken** (short TTL, scoped permissions, signed) → encrypt with device PIN via WebCrypto / Tauri Stronghold | **REQUIRED** |
| Biometric unlock | Optional native plugin; decrypts vault only |
| Role change / permission revoke | Requires online refresh; offline token honors `exp` + embedded permission bitmap |

Implementation sketch (Wave C):

- Model: `DeviceRegistration` (user, school, device_id, public_key, last_seen, revoked_at)
- API: `POST /api/v1/devices/offline-token/` (online only) → returns encrypted-capability blob
- Client: `rmc-offline-auth-vault.js` — PBKDF2 + AES-GCM; no raw token in localStorage

### 2.5 LAN mesh without CouchDB (Wave G — optional but innovative)

When entire school lacks internet but has Wi‑Fi:

1. **Hub mode (preferred):** Admin laptop runs `RMC_DEPLOYMENT_PROFILE=edge` Django — all devices sync to hub IP (mDNS `_runmycampus-hub._tcp.local.`).
2. **Data-mule mode (no hub PC):** Designated device exports **signed delta bundle** (`application/x-rmc-sync-bundle+ndjson`) over local HTTP POST to peer; peer merges into local Dexie; mule device syncs to cloud when it gets 3G.

No port 5984. No CouchDB. Replication = **your existing delta sync format** + HMAC device signature.

### 2.6 Conflict resolution (do not simplify)

Keep [`DEFAULT_STRATEGY_PER_ENTITY`](../apps/sync_engine/conflict_resolver.py):

- Attendance / notes → LWW
- Grades / payments → **manual_review** always
- Permissions → server_authoritative

Client-side-only “newest timestamp wins” for grades is **forbidden**.

### 2.7 Seven-layer configurability (mandatory — platform + tenant)

**Nothing hardcoded.** Every SODP knob routes through the existing cascade:

| Layer | Offline / sync | Email delivery |
|---|---|---|
| **1. Platform env** | `RMC_DEPLOYMENT_PROFILE`, `RMC_AUTO_APPLY_OFFLINE_BUNDLE_ON_PROVISION` | `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` |
| **2. Platform operator JSON** | Global Feature Control (`enable_offline_mode`, per-domain toggles in `views_feature_control.py`) | `SiteSettings.email_delivery` (existing — `/super/email/configure/`) |
| **3. Tenant school JSON** | `School.settings["offline_delivery"]` (NEW) — hub URL, mesh mode, queue caps, allowed action types | `School.settings["email_delivery"]` (NEW) — tenant-owned SMTP / API provider |
| **4. Tenant SiteSettings / policy** | `enable_offline_mode` + policy registry `offline_mode` capability | `SiteSettings` communication fields where applicable |
| **5. User prefs** | Device PIN / biometric opt-in (client vault) | Notification locale per user |
| **6. Feature flags** | Per-domain SW queue toggles in `SMS_OFFLINE_CONFIG` | `notify.*` intent enablement per template family |
| **7. DB fixture / constant** | Default conflict strategies in `conflict_resolver.py` | Default retry backoff in `email_delivery.py` |

**Email resolution order (server-side only — never on client):**

```
tenant School.settings["email_delivery"]  (if enabled + school admin configured)
    ↓ else
platform SiteSettings.email_delivery        (operator override — existing)
    ↓ else
Django env / Anymail / Resend               (Render default)
```

Refactor `get_resolved_smtp_config()` → `get_resolved_smtp_config(*, school=None)` with the cascade above. Passwords stored **encrypted** (reuse Fernet pattern from `forms_email_delivery.py`). Tenant UI: **Studio OS → Infrastructure → Email & notifications** (or Communication Center) with **Test connection** probe (reuse `smtp_probe`).

**Tenant-owned SMTP contract:**

- School brings their own server (Google Workspace, Microsoft 365, cPanel, regional host) — platform never stores credentials on devices.
- Tenant admin enters host/port/TLS/user/password once online; offline queue holds **notification intents** only; on sync Django sends using **tenant-resolved** SMTP.
- Operator can **disable** tenant SMTP (platform-only mode) via platform policy flag `allow_tenant_email_delivery_override`.

**Offline resolution order:**

```
School.settings["offline_delivery"]  (hub URL, mesh enabled, max queue, profile hint)
    ↓ merged with
Feature Control flags + offline_mode_bundle
    ↓ exposed to client as
SMS_OFFLINE_CONFIG in portal_base (existing pattern)
```

New module: `apps/schools/offline_delivery_settings.py` + `apps/schools/email_delivery_settings.py` — mirror `data_residency_settings.py` validation bridge pattern.

---

## 3 — Wave breakdown (implementation batches)

### Wave A — batch **1406**: Offline foundation hardening

**Goal:** Close every item in `OFFLINE_MODE_GAPS.md` service-worker section + unified action types.

**Deliverables:**

1. `apps/platform_runtime/offline_action_types.py` — enum + JSON schema validators
2. Service worker patches:
   - Strip Cookie/CSRF from stored replay headers
   - 4xx → failed store; 5xx → backoff (existing, verify complete)
   - Sort replay by `createdAt`
   - Queue max size from `SMS_OFFLINE_CONFIG.maxQueueItems`
   - Extend `isApiWriteRequest` for `/api/entity/`, `/api/requests/`, `/portal/api/offline/`
3. `static/js/offline-status-bar.js` — queue cap warning UX
4. Migration: `OfflineAction.client_idempotency_key` unique per `(school, key)` if not present
5. **`scripts/verify_sovereign_offline_foundation.py`** → `SOVEREIGN_OFFLINE_FOUNDATION_PASS`
6. **`apps/schools/offline_delivery_settings.py`** — tenant `School.settings["offline_delivery"]` bridge + validation
7. Tenant admin UI stub: Studio OS Infrastructure → Offline & sync (hub URL, mesh toggle, queue cap) — reads/writes school JSON
8. Django tests: `apps/platform_runtime/tests/test_offline_action_types.py`, `apps/schools/tests/test_offline_delivery_settings.py`

**Proof:**

```bash
python scripts/verify_sovereign_offline_foundation.py
python scripts/verify_online_edge_dual_mode.py
python manage.py test apps.platform_runtime.tests.test_offline_action_types --noinput
```

**SW bump:** `sms-v3.65.0-sovereign-offline-foundation-wave-a-2026-05-23`

---

### Wave B — batch **1407**: Server-owned messaging + dual-state delivery + tenant SMTP

**Goal:** 10× email reliability; online instant + offline queued **intents**; zero client SMTP; **full platform + tenant email configurability**.

**Deliverables:**

1. `apps/schoolops/notification_intent.py` — dispatch table: `template_key` → renderer → `send_transactional(school=...)`
2. Wire offline queue handler: `action_type.startswith("notify.")` → `dispatch_notification_intent()`
3. **`apps/schools/email_delivery_settings.py`** — read/validate/save `School.settings["email_delivery"]`; encrypted password round-trip (same contract as operator form)
4. **Refactor** `get_resolved_smtp_config(*, school=None)` — cascade: tenant → operator SiteSettings → env
5. **Tenant admin UI** — SMTP configure + test probe at `/school/studio/infrastructure/email/` (or Communication Center stem); RBAC: school admin only; never expose password on GET
6. **Operator policy toggle** — `allow_tenant_email_delivery_override` in platform Feature Control / SiteSettings
7. Idempotency: `EmailDeliveryEvent.idempotency_key` + `OfflineAction.client_idempotency_key`
8. Celery task `schoolops.deliver_notification_intent` — async path; passes resolved `school_id` for SMTP cascade
9. Extend `verify_email_delivery_surface.py` — tenant cascade + intent dispatch + no plaintext password in API responses
10. **`scripts/verify_tenant_email_delivery_cascade.py`** → `TENANT_EMAIL_DELIVERY_CASCADE_PASS`
11. Operator + tenant docs in `EMAIL_DELIVERABILITY.md` — tenant BYO-SMTP section
12. Portal UI: notification queue badge in offline sync bar

**Proof:**

```bash
python scripts/verify_email_delivery_surface.py
python scripts/verify_tenant_email_delivery_cascade.py
python manage.py test apps.schoolops.tests.test_notification_intent apps.schools.tests.test_email_delivery_settings --noinput
```

**SW bump:** `sms-v3.66.0-sovereign-notification-intents-wave-b-2026-05-23`

---

### Wave C — batch **1408**: Offline auth + device vault

**Goal:** Bank-grade offline login without local password hashes.

**Deliverables:**

1. Models + migration: `DeviceRegistration`, `OfflineCapabilityToken` (or JWT blacklist compatible)
2. API views under `apps/accounts/` or `apps/api/` — DRF, `@extend_schema`, tenant-scoped
3. `static/js/rmc-offline-auth-vault.js` — WebCrypto PIN wrap
4. Tauri: document Stronghold integration in `companion-tauri/README.md` + stub command
5. **`scripts/verify_offline_auth_contract.py`** — refuses password hash export markers in client code
6. Tests: token expiry, revoked device, permission scope

**Proof:**

```bash
python scripts/verify_offline_auth_contract.py
python manage.py test apps.accounts.tests.test_offline_capability_token --noinput
```

---

### Wave D — batch **1409**: Tauri Field Client v1

**Goal:** Desktop executable for attendance + grade entry + sync; reuse portal UI.

**Deliverables:**

1. New product crate OR extend `companion-tauri/` with `field-client` feature flag
2. Load tenant portal URLs in WebView; inject `window.RMC_FIELD_CLIENT=1`
3. Native: secure token storage (Stronghold), auto-sync loop calling existing APIs
4. Optional: `tauri-plugin-sql` local cache mirroring Dexie schema (read-only mirror)
5. Build scripts + `docs/FIELD_CLIENT_TAURI_OPERATOR.md`
6. **`scripts/verify_field_client_scaffold.py`** — manifest, CSP, no forbidden network hosts

**Proof:**

```bash
python scripts/verify_field_client_scaffold.py
cd companion-tauri && cargo check
```

**Honest residual:** Apple notarization / Windows Authenticode = Lane 2 (reuse `COMPANION_SIBLINGS_SIGNED_RELEASE.md`)

---

### Wave E — batch **1410**: Capacitor Android shell

**Goal:** Tablet-friendly shell for parents/teachers; same APIs.

**Deliverables:**

1. `companion-capacitor/` scaffold (or `apps/mobile-shell/`) — `capacitor.config.json` per plan
2. `@capacitor-secure-storage-plugin` for tokens
3. `cleartextTrafficPermitted` only for debug LAN hub builds
4. PWA manifest parity + install prompt
5. **`scripts/verify_capacitor_shell_scaffold.py`**

**Proof:**

```bash
python scripts/verify_capacitor_shell_scaffold.py
```

---

### Wave F — batch **1411**: Edge hub + mDNS + hybrid failover

**Goal:** Zero-config school LAN hub discovery; hybrid cloud→hub retry.

**Deliverables:**

1. Rust mdns-sd in Tauri hub mode OR Python sidecar for edge install
2. Service type: `_runmycampus-hub._tcp.local.`
3. `SMS_OFFLINE_CONFIG.hubBaseUrl` + SW cloud-failover fetch wrapper
4. Polish `scripts/install_local_hub.sh` — single-command edge profile
5. Extend `verify_online_edge_dual_mode.py` with mDNS + hybrid checks
6. Doc update: `LOCAL_HUB_MODE.md` § mDNS

**Proof:**

```bash
python scripts/verify_online_edge_dual_mode.py
python scripts/verify_sovereign_offline_foundation.py
```

---

### Wave G — batch **1412**: LAN data-mule + E2E certification

**Goal:** Peer delta export when no hub; Playwright proof; GEOS evidence.

**Deliverables:**

1. `apps/sync_engine/delta_bundle.py` — export/import signed NDJSON bundles
2. API: `POST /api/v1/sync/bundle/upload/` (staff-only, device signature verify)
3. Client: `rmc-lan-mule-sync.js` — optional peer transfer over local network
4. **`tests/e2e/offline-queue-replay.spec.js`** — offline → queue → online → assert DB
5. Evidence JSON: `var/evidence/geos-99/offline/sovereign_delivery_e2e_<date>.json`
6. Extend `verify_greatest_education_os_matrix.py` pilot flags if applicable

**Proof:**

```bash
python scripts/verify_sovereign_offline_e2e_scaffold.py
npx playwright test tests/e2e/offline-queue-replay.spec.js
```

**SW bump:** `sms-v3.70.0-sovereign-offline-e2e-wave-g-2026-05-23`

---

## 4 — Security invariants (CI-enforced)

Add to Wave A/C verifiers; fail closed:

| Invariant | Enforcement |
|---|---|
| No client `SEND_EMAIL` / raw SMTP fields in offline payloads | AST scan in `verify_sovereign_offline_foundation.py` |
| No `@csrf_exempt` on sync views | `audit_security_surface.py` + new scan |
| No `tenant_id` trust from JSON body | grep + test: tenant from `request.user` / session school |
| No password hash in client storage keys | `verify_offline_auth_contract.py` |
| Grades conflict auto-merge forbidden | test: `grade.submit` → manual_review strategy |
| PII in outbox logs forbidden | `scan_pii_logging_smell` baseline 0 |
| All DRF sync views have `@extend_schema` | `scan_drf_schema_coverage` baseline 0 |

---

## 5 — Simplicity & ease-of-use (product rules)

1. **One sync button** — header “Sync now” works identically on PWA, Tauri, Capacitor.
2. **Plain language status bar** — reuse `offline-queue-client.js` copy patterns; no jargon.
3. **Automatic sync on reconnect** — already in `OFFLINE_SYNC_WHEN_INTERNET_RETURNS.md`; do not regress.
4. **School operator setup ≤ 3 steps:** install hub **or** bookmark cloud PWA **or** install Field Client MSI/DMG.
5. **No IP typing** — mDNS resolves hub; QR code encodes `{origin, tenant_slug}` for classroom tablets.
6. **Feature Control toggles** — per-domain offline sync kill switches in existing bundle.

---

## 6 — Agent handoff checklist (§11 — start here)

When picking up implementation:

1. Read this plan §0–§2 (architecture invariants — do not violate).
2. Claim **one wave** (batch 1406–1412) in SOT §11.4 before coding.
3. Run Phase 0 verifiers baseline:

```bash
python scripts/verify_online_edge_dual_mode.py
python scripts/verify_email_delivery_surface.py
python manage.py check
```

4. Implement smallest diff; match existing patterns in cited files.
5. Add wave verifier + tests **before** claiming DONE.
6. Bump SW on any static JS/CSS change.
7. Update SOT §11.4 row + `RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md` A–F after green proof.
8. Run `python scripts/generate_system_closure_map.py --write` if queue status changes.

**Do NOT:**

- Create parallel plan markdown outside this file
- Introduce RxDB/PouchDB/CouchDB replication
- Send email from client payloads
- Skip conflict policies for grades/payments

---

## 7 — Lane 2 (operator / external) — honest blockers

| Item | Owner | Evidence path |
|---|---|---|
| Resend/Anymail API keys on Render | Platform ops | `/super/email/health/` green probe |
| SPF/DKIM/DMARC DNS | School IT | `EMAIL_DELIVERABILITY.md` checklist |
| Tauri signed release | Infra | `var/evidence/companion-tauri/` |
| Playwright on Render staging | QA | `var/evidence/geos-99/offline/` |
| Google Play listing | Product | App store console (Wave E+) |

Repo-complete ≠ corridor-live. Matrix stays honest (`live=0%` until evidence).

---

## 8 — Verifier registry (new)

| Script | Wave | Pass string |
|---|---|---|
| `verify_sovereign_offline_foundation.py` | A | `SOVEREIGN_OFFLINE_FOUNDATION_PASS` |
| `verify_tenant_email_delivery_cascade.py` | B | `TENANT_EMAIL_DELIVERY_CASCADE_PASS` |
| `verify_sovereign_offline_config_cascade.py` | A+B | `SOVEREIGN_OFFLINE_CONFIG_CASCADE_PASS` |
| `verify_offline_auth_contract.py` | C | `OFFLINE_AUTH_CONTRACT_PASS` |
| `verify_field_client_scaffold.py` | D | `FIELD_CLIENT_SCAFFOLD_PASS` |
| `verify_capacitor_shell_scaffold.py` | E | `CAPACITOR_SHELL_SCAFFOLD_PASS` |
| `verify_online_edge_dual_mode.py` (extended) | F | `ONLINE_EDGE_DUAL_MODE_PASS` |
| `verify_sovereign_offline_e2e_scaffold.py` | G | `SOVEREIGN_OFFLINE_E2E_SCAFFOLD_PASS` |

Wire into `verify_phases_3_11_gates.py` after Wave A lands.

---

## 9 — SOT batch map

| Batch | Wave | Status at plan authorship |
|---|---|---|
| **1405** | Program reservation + this plan | **PLANNED** |
| **1406** | A — Offline foundation | NOT STARTED |
| **1407** | B — Notification intents | NOT STARTED |
| **1408** | C — Offline auth vault | NOT STARTED |
| **1409** | D — Tauri Field Client | NOT STARTED |
| **1410** | E — Capacitor Android | NOT STARTED |
| **1411** | F — Edge mDNS + hybrid | NOT STARTED |
| **1412** | G — LAN mule + E2E | NOT STARTED |

---

## 10 — Definition of done (whole program)

Program is **REPO-COMPLETE** when:

1. Waves A–G each have green named verifiers + targeted tests
2. `OFFLINE_MODE_GAPS.md` items marked closed or superseded with proof links
3. No client email SMTP path exists in tree (scanner enforced)
4. **Tenant + operator email cascade** green (`verify_tenant_email_delivery_cascade.py`)
5. **All offline/sync knobs** exposed via platform Feature Control + tenant Studio Infrastructure UI (no magic constants in client JS)
6. E2E Playwright offline replay spec passes locally
7. SOT batches 1406–1412 marked **DONE** with honest Lane 2 residuals only for store/signing/DNS

Program is **CORRIDOR-LIVE** only after Lane 2 evidence in `var/evidence/geos-99/offline/`.

---

*End of plan — build agent executes §6 checklist starting at batch 1406 Wave A.*
