# Glocal Local-First Sovereignty — Implementation Plan

**Status:** plan (2026-06-07). Converts the owner's "RunMyCampus-as-dominant-infrastructure / Cloud-Dependency-Collapse" manifesto into a grounded, phased plan mapped onto the **real** codebase. The strategic thesis is sound and **already substantially realized**; this doc separates that signal from the manifesto's harmful code, and sequences the genuine gaps.

Companion SOTs: `docs/MARKETING_REDESIGN_DIRECTION.md` (§3–§4 reject-list + regional competitor table), `apps/schools/feature_gap_register.py` (per-feature promise/proof SOT — lifecycle rows added 2026-06-07), `docs/LOCAL_HUB_MODE.md` + `docs/RESILIENT_EDGE_IMPLEMENTATION_STATUS.md` (existing offline architecture).

---

## 0. Verdict — signal vs noise

The manifesto's thesis — *treat the internet as a transport variable, not a runtime requirement; run with full capability on a disconnected local node and stream compressed deltas up when a signal is caught* — is **the right strategy and is already the platform's direction**. Exploration confirms a mature offline-first stack already ships (see §2). So this is mostly **finish + productize + prove**, not greenfield.

Three buckets:

| Bucket | What | Action |
|---|---|---|
| **Adopt (strategy)** | Local-first sovereignty, the 6-phase lifecycle framing, the regional competitor audit (PART 1), region-aware payments/messaging, ambient capture, vocabulary injection | Use as roadmap + messaging. Most primitives exist; gaps sequenced in §5. |
| **Reject (harmful code, PART 3)** | `apps/glocal_kernel` (invented app), the JWT-shard-per-tenant connection-injection middleware, hardcoded DB credentials, the naive last-write-wins "CRDT" serializer, the `100dvh`/`overflow:hidden`/`edos-text-shield` viewport-lock base template, the inline-style "self-healing sentinel" JS | Do **not** apply. Reasons + real equivalents in §1. |
| **Reject (process, PART 4)** | The "audit + refactor ALL files across the entire workspace, run without exit until 100%" blind-sweep prompt | Conflicts with `CLAUDE.md` scope discipline and the owner's own "validate before continuing" rule. Already guard-railed in `MARKETING_REDESIGN_DIRECTION.md` §3.3. |

---

## 1. Reject list — PART 3 code, with reasons and the real equivalent

These are the same anti-patterns already diagnosed as the cause of the marketing-page blank-box/clipping bugs, plus new architectural mismatches. **None of the pasted PART 3 code should be merged.**

| Pasted artifact | Why it's wrong here | The real subsystem to use instead |
|---|---|---|
| `apps/glocal_kernel/models.py` + `GlocalTenantProfile` + `AmbientTelemetryLog` | `apps/glocal_kernel` **does not exist and must not be created**. It duplicates real models. | Tenant config SOT is the `School` model + the `RuntimeDefaults → SiteSettings` cascade (`CLAUDE.md` "Tenant config cascade"). Localization SOT is `apps/siteconfig/country_localization_service.py`. Telemetry rides `apps/observability/` + `apps/sync_engine`. |
| `post_migrate` signal injecting Postgres RLS `CREATE POLICY` against `request.jwt.claim.tenant_id` | We already enforce RLS — but via `app.current_school_id` (a Postgres GUC), set per-request in `apps/schools/middleware.py`, policy in migration `apps/schools/migrations/0002_enable_rls_postgresql.py`. A second, JWT-claim-keyed policy would **conflict** with the live one. | `apps/schools/rls_context.py` (`set_rls_school_id`, `rls_school()`), `rls_readiness.py`. Don't add a parallel RLS scheme. |
| `CongruentTenantMeshMiddleware` — dynamic per-tenant DB creation, one Postgres database **per tenant** (`db_shard_<tenant_id>`), connection injection at request time | Our model is **shared-DB, row-scoped** (School + RLS), with an *optional* django-tenants schema mode behind `USE_DJANGO_TENANTS`. A DB-per-tenant router is a different, unbuilt architecture that would break every existing query, migration, and the RLS gate. | Existing middleware stack (RLS or schema mode, chosen by env). `apps/schools/channels_tenant_middleware.py` already verifies tenant claims on the WS layer. |
| `'PASSWORD': 'SECURE_ENV_DECRYPTED_PASSWORD'`, `'HOST': 'eu-central-1.pgbouncer...'` hardcoded in middleware | **Hardcoded secrets + hardcoded region host.** Violates the no-hardcoding directive and is a credential-leak risk. | `DATABASE_URL` env-driven config in `config/settings.py`. Nothing routes through a literal. |
| `VisualTelemetryPayloadSerializer.merge_offline_crdt_stream` — "CRDT" that is actually last-write-wins by string-compared timestamp | This is **not** a CRDT (no convergence guarantee; wall-clock string compare across edge nodes silently loses concurrent writes; `Date.now()` skew = data loss). | `apps/sync_engine/` + `apps/api/mobile_api.OfflineSyncQueue` + `apps/api/offline_encryption.py`. Extend the real queue/merge logic; don't bolt on a naive merger. |
| `templates/portal_base.html` rewrite: `html{... overflow:hidden}`, `height:100dvh` grid lock, `.edos-text-shield{white-space:nowrap;text-overflow:ellipsis;overflow:hidden}`, `user-scalable=no` | This is **literally** the pattern that clipped pages into blank boxes and truncated/doubled headings (`MARKETING_REDESIGN_DIRECTION.md` §3, §7). Also a WCAG 1.4.10 reflow + 1.4.4 zoom failure (`user-scalable=no`). | Real shells: `templates/portal_base.html`, `base.html`, `control_plane_skeleton.html`, `admin/base_site.html`, `marketing/base_marketing.html` — responsive flow, `min-height:100svh` cadence, content never clipped. Token system + `.rmc-*` grammar (`CLAUDE.md`). |
| Inline-`<script>` "layout sentinel" that POSTs overflow metrics and mutates `element.style.*` (font-size/whitespace/padding) at runtime | Runtime inline-style mutation **bypasses the token system** and trips `scan_inline_style_off_token` (baseline 0) + CSP (`verify_csp_nonce_emission`). "Auto-fix overflow by clipping" re-introduces the clipping bug it claims to detect. | Fix overflow at authoring time with the token/grammar system. Overflow risk is already gated by `scan_horizontal_overflow_risk.py`. |

**Net:** keep the *intent* (telemetry, offline merge, RLS isolation, region routing, dense premium chrome). Reject every line of the pasted *implementation* — each one either invents a non-existent subsystem, contradicts the live architecture, hardcodes a secret, or re-introduces a known UI bug.

---

## 2. The real architecture (so nobody rebuilds it)

Verified by exploration on 2026-06-07. **This already exists — do not recreate it.**

- **Tenancy:** shared Postgres DB + `School` tenant model + RLS via `app.current_school_id` GUC (`apps/schools/middleware.py`, `rls_context.py`, migration `0002_enable_rls_postgresql.py`). Optional multi-schema mode behind `USE_DJANGO_TENANTS`. Dev = SQLite (`db_working.sqlite3`); prod = Postgres via `DATABASE_URL`.
- **Offline-first stack:** `static/js/service-worker.js`, `static/js/offline-db.js` (IndexedDB), `apps/sync_engine/` (orchestration), `apps/api/mobile_api.OfflineSyncQueue`, `static/js/sync-manager.js`, `static/js/offline-queue-client.js`, `static/js/rmc-lan-mule-sync.js` (LAN hub sync), `apps/api/offline_encryption.py` (session-scoped HMAC-SHA256 queue key), offline auth vault (`rmc-offline-auth-bootstrap.js`, `rmc-offline-auth-vault.js`).
- **Offline feature flags:** `apps/platform_runtime/offline_mode_bundle.py` — `enable_offline_form_queue`, `enable_offline_attendance_sync`, `enable_offline_grade_sync`, `enable_offline_payment_sync`, `enable_offline_background_sync`, `enable_offline_queue_encryption`, `offline_entity_sync`, `offline_requests_sync`.
- **Region/geo + payments:** `apps/schools/marketing_geo_context.py`, `apps/schools/marketing_media_matrix.py` (`apm_icons_for_country`), `apps/schools/marketing_channel_rails.py`, `apps/finance/payment_region_catalog.py` (+ `gateways/paystack.py`, `gateways/razorpay.py`). Localization SOT: `apps/siteconfig/country_localization_service.py`.
- **Edge/AI posture:** `services/ai_deployment_posture.py` maps `RMC_DEPLOYMENT_PROFILE` (`edge` → Ollama; `online` → cloud). Doc: `docs/AI_DEPLOYMENT_POSTURE.md`.

---

## 3. Regional competitor audit (manifesto PART 1)

Already captured as a per-section messaging SOT in `docs/MARKETING_REDESIGN_DIRECTION.md` §4 (North America / LATAM / EU-UK / Sub-Saharan-N.Africa / APAC-South-Asia → competitor → gap → our 10X angle → which section proves it). **No duplication here** — that table is the source of truth; fold-in rule (reconcile every claim against `feature_gap_register` + `public_product_promise_matrix`, keep illustrative badges) stands.

---

## 4. The 6-phase institutional lifecycle (manifesto PART 2) → real apps + honest status

Status legend: **SHIPPED** = primitive verified present · **PARTIAL** = primitive exists, productized lifecycle flow incomplete · **ABSENT** = verified not built. **All statuses below were evidence-checked on 2026-06-07** (discovery pass over the named apps — see §4.1 for the receipts); none are assumed. Register slug = the `feature_gap_register.py` row tracking it.

### Phase 1 — Onboarding, sharding & setup studio (pre-year)
| Manifesto tool | Real home | Status | Register slug |
|---|---|---|---|
| Dynamic intake wizards (offline IndexedDB cache) | `apps/setup_studio`, `apps/schools` signup, `offline-db.js` | PARTIAL | `offline-intake-wizard` |
| Sovereign data router (shard PII by signup country) | `School` + RLS (`apps/schools`), `apps/compliance` | SHIPPED (RLS) / PARTIAL (residency pinning) | `data-residency-routing` |
| Cultural vocabulary injector (Student→Learner/Cadet) | `apps/locale`, `country_localization_service.py` | PARTIAL | `vocabulary-injector` |
| Resource allocation / timetable solver (offline, conflict-free) | `apps/academics/timetable_solver.py` (+ `views_timetable_solver.py`) | PARTIAL (greedy kernel; CSP solver deferred) | `timetable-solver` |

### Phase 2 — Roster orchestration & human capital (week 1)
| Manifesto tool | Real home | Status | Register slug |
|---|---|---|---|
| Dual-identity profile matrix (school + evening coaching) | `apps/student360`, `apps/people` | PARTIAL | `dual-identity-profile` |
| Labor-contract / payroll blueprint (offline tax/pension) | `apps/payroll` | PARTIAL | (existing payroll) |
| 1-click substitute broker (absence → WhatsApp/SMS broadcast) | `apps/schoolops/substitute_handover.py` (+ views/forms) | PARTIAL (handover packet ships; auto-find + broadcast GAP) | `substitute-broker` |

### Phase 3 — Financial ledger & marketplace (daily)
| Manifesto tool | Real home | Status | Register slug |
|---|---|---|---|
| Split-wallet checkout (80/10/10 multi-vendor split) | `apps/finance`, `apps/billing` | PARTIAL (router exists; productized split flow incomplete) | `split-wallet-checkout` |
| Cashless campus POS (QR / RFID / biometric → wallet debit) | `apps/api/pos_checkout_api.py` + `apps/schoolops/pos_checkout.py` (migration 0024) | ✅ SHIPPED (Wave C) | `cashless-campus-pos` |
| Allergen barrier (health → cafeteria sale-block at terminal) | `pos_checkout.allergen_conflict` vs `schoolops.HealthRecord` | ✅ SHIPPED (Wave C) | `allergen-barrier-pos` |
| Fiscal e-invoice adapters (SAT/SEFAZ stamped invoices) | `apps/finance/payment_region_catalog.py` | PARTIAL | `fiscal-einvoice-adapters` |

### Phase 4 — Ambient classroom execution (daily learning)
| Manifesto tool | Real home | Status | Register slug |
|---|---|---|---|
| Proximity attendance ingest (device-agnostic: BLE/RFID/NFC/QR) | `apps/api/proximity_attendance_api.py` + `apps/academics/proximity_attendance.py` | ✅ SHIPPED (Wave B) | `bluetooth-proximity-attendance` |
| OCR marksheet scan-grading → gradebook | `apps/evals/ocr.py` → `evals.Evaluation` | ✅ SHIPPED | `omr-scan-grading` |
| Plickers-style card-sweep (no-device camera shape-parse) | `apps/evals` (CV, future) | GAP (distinct from OCR) | `plickers-card-sweep` |
| Zero-data homework queue buffer (<500KB cache, gate sync) | `apps/sync_engine`, `offline_mode_bundle.py`, `offline-db.js` | PARTIAL (offline queue exists; homework-buffer flow not built) | `zero-data-homework-buffer` |

### Phase 5 — Transit ops & event logistics
| Manifesto tool | Real home | Status | Register slug |
|---|---|---|---|
| Smart fleet route optimizer (offline map files) | `apps/schoolops` | ⛔ BLOCKED — `schoolops.Stop` has no lat/lng; needs a geo field first | `smart-fleet-route-optimizer` |
| Non-phone RFID/NFC/QR boarding monitor → parent feed | `apps/api/boarding_monitor_api.py` + `apps/schoolops/boarding_monitor.py` (migration 0025) | ✅ SHIPPED (Wave D) | `rfid-fleet-monitor` |
| Field-trip compliance factory (e-sign + offline medical checklist) | `compliance.ConsentRequest`/`ConsentRecord` | PARTIAL (consent pipeline exists; dedicated surface + medical checklist pending) | `field-trip-compliance` |

### Phase 6 — Compliance shutdown & auditing (end-of-year)
| Manifesto tool | Real home | Status | Register slug |
|---|---|---|---|
| One-click auditor gateway (time-bounded magic link, PII masking, access log) | `apps/compliance/auditor_access.py` + `views_auditor.py` + `pii_masking.py` (migration 0016) | ✅ SHIPPED (Wave E) | `auditor-magic-link` |
| Predictive retention / cash-flow analytics | `apps/analytics`, `apps/reports` | PARTIAL | (existing analytics) |
| Non-repudiation logger (signed, append-only action log) | `apps/compliance/non_repudiation.py` + `NonRepudiationLogEntry` (migration 0017) | ✅ SHIPPED (Wave E tail) | `non-repudiation-logger` |
| GDPR cryptographic key-shredding (Right-to-be-Forgotten, preserve aggregates) | `apps/compliance` (`EraseRequest` + `gdpr_services`) | PARTIAL | `gdpr-key-shredding` |
| State-reporting bridges (CALPADS / EdFacts / etc.) | `apps/reports/state_reporting.py` (column maps + CSV) + `export_state_report` | ✅ SHIPPED (Wave E tail) | `state-reporting-bridges` |
| CRDT offline convergence (LWW + G-set + multi-terminal wallet) | `apps/sync_engine/crdt.py` + `crdt_wallet.py` | ✅ SHIPPED (Wave F) | `crdt-offline-convergence` |

### 4.1 Discovery-pass receipts (2026-06-07)

Every status above was checked against the named app, not assumed. Result: **6 of the 10 candidate gaps already have real primitives** (PARTIAL), **4 are genuinely ABSENT**. This is exactly why the verify-before-claim discipline matters — over half the "gaps" weren't.

- **PARTIAL (primitive exists):** `timetable-solver` (`apps/academics/timetable_solver.py` greedy kernel) · `substitute-broker` (`apps/schoolops/substitute_handover.py` redacted handover packet) · `cashless-campus-pos` (`apps/setup_studio/wizards/cashless_campus_pos.json` + `wizard_resolvers.py`) · `allergen-barrier-pos` (POS wizard allergen step + `food_block` in `schoolops/migrations/0012`) · `omr-scan-grading` (`apps/evals/ocr.py`, pytesseract + confidence) · `state-reporting-bridges` (`apps/platform_runtime/statutory_tenant_extract.py` + `emis/org_aggregate`).
- **ABSENT (verified, no trace):** `bluetooth-proximity-attendance` (RUM beacons are Web-Vitals telemetry, unrelated) · `smart-fleet-route-optimizer` (registered as a marketplace capability stub `transport-route-optimizer`, no algorithm) · `rfid-fleet-monitor` (only lost-belongings QR in `schoolops/lost_belongings_qr.py`) · `auditor-magic-link` (`compliance_auditor` mgmt command is a health-check, not a gateway).

Register statuses were corrected to match: the 6 PARTIAL rows are now `in_progress` (with the verified file path in `notes`); the 4 ABSENT rows stay `planned` (notes record the verification so the search isn't repeated).

---

## 5. Sequenced delivery (genuine gaps only)

Scope discipline per `CLAUDE.md`: each wave is bounded, lands its cascade/primitive first, HTML/test-validates before adoption, bumps the SW, and flips its `feature_gap_register` row to `shipped` **only** when a real proof (route/model/command/CI gate) resolves.

**Wave A — Prove what already exists (cheapest, highest trust). ✅ DONE 2026-06-07.** Audited every `in_progress` lifecycle row for a *resolving* proof. **4 flipped to `shipped`**, each backed by a proof the register test verifies: `data-residency-routing` (`verify_data_residency` cmd + `schools.School.data_region`), `vocabulary-injector` (new `verify_terminology_cascade` cmd over the 6-layer `terminology_service` cascade), `split-wallet-checkout` (`finance:split_allocation` + `finance.InvoicePayerShare`; `test_split_allocation` 2/2), `gdpr-key-shredding` (relabelled honestly to **RTBF erasure/anonymization** — `compliance.EraseRequest` + `process_erase_requests` cmd; literal crypto key-shred remains a future upgrade). **1 downgraded to `planned`**: `fiscal-einvoice-adapters` (only `tax_engine.py` rate tables exist; zero NF-e/CFDI code). The rest stayed `in_progress` with sharpened notes (`non-repudiation-logger` = migration_cloud-scoped only; `offline-intake-wizard`, `zero-data-homework-buffer`, `field-trip-compliance` = primitive only). **Bug found + fixed during validation:** the payment-reminder email path (`apps/finance/tasks.py`) recorded a *failed* email as `SENT` (the "audit H1" `send_transactional` refactor swallowed failures; the guarding test patched the long-removed `EmailMessage.send`). Fixed: `_send_payment_email` now returns a bool, the caller writes a `FAILED` log on failure, and the test patches the real `send_transactional`. Finance split suite 20/20; `manage.py check` 0; money-float/bare-except/pii-logging 0; register 7/7.

**Wave B — Ambient capture (Phase 4). ✅ DONE 2026-06-07.** Built **device-agnostic proximity attendance ingest** migration-free: `POST /api/proximity/attendance/ingest/` (`ProximityAttendanceIngestAPI`) → `academics/proximity_attendance.record_proximity_checkin` queues an offline `ATTENDANCE` action (idempotent per device+student+date) that drains into a real `academics.Attendance` row with a proximity audit remark; reuses the existing `enqueue_offline_action`/`_apply_attendance` pipeline (no new model/ActionType), new flag `enable_offline_proximity_attendance_sync`. Tests `test_proximity_attendance` 6/6. **OMR scan-grading** was found already shipped (OCR `process_marksheet_upload` → `teacher_marks_entry` → `_apply_ocr_entries` → `evals.Evaluation`) and flipped to `shipped`; the genuinely-distinct **Plickers card-sweep** (computer-vision, not text OCR) was carved out as its own `planned` row `plickers-card-sweep`. Gates: register 7/7 (both new routes reverse, both proof models load), DRF schema 0 undocumented, `check` 0, print/bare-except 0, migration drift none. No SW bump (no browser-cached asset changed).

**Wave C — Campus commerce (Phase 3). ✅ DONE 2026-06-07.** (Split-wallet was shipped in Wave A.) Built **cashless campus POS checkout** — `POST /api/pos/checkout/` (`PosCheckoutAPI`) → `schoolops/pos_checkout.checkout`: resolves the student by id or scanned credential (`student_code`), enforces the **allergen barrier** (`allergen_conflict` cross-refs `schoolops.HealthRecord` allergy rows + Allergy tags against the item label → refuses the sale with 409 before any debit), then debits `schoolops.MealPlanBalance` atomically (Decimal-safe, `select_for_update`) and records a student-linked `PosSaleLine`. Added `student` FK + `idempotency_key` to `PosSaleLine` (migration `0024`, additive/nullable). Idempotent per key (no double-charge on retry); allergen enforcement honours the POS wizard `allergen_dietary_rules` setting, safety-first default ON. Tests `test_pos_checkout` 8/8. Gates: register 7/7 (route reverses, both models load), migration drift clean, `check` 0, DRF schema 0, money-float 0. **Honest deferral:** true multi-terminal *offline* wallet debit (double-spend reservation) is out of scope here and belongs with Wave F's CRDT work.

**Wave D — Logistics (Phase 5). ◑ PARTIAL 2026-06-07 (boarding shipped).** Built the **non-phone RFID/NFC/QR boarding monitor** — `POST /api/transport/boarding/ingest/` (`BusBoardingIngestAPI`) → `schoolops/boarding_monitor.record_boarding` writes an append-only, idempotent `BusBoardingEvent` (migration `0025`), resolves the route from the student's `TransportAssignment`, fires a best-effort guardian notify (`parent_notified`). Append-only + idempotent = offline-safe by construction. Tests `test_boarding_monitor` 5/5; gates register 7/7, migration drift clean, check/DRF/print/bare-except 0. **Now FULLY CLOSED 2026-06-07:** (a) **route optimizer** — added `Stop.latitude/longitude` (migration `0026`) + `schoolops/route_optimizer.py` (haversine + greedy nearest-neighbour, offline, two-phase sequence persist) + `optimize_bus_route` command; tests 7/7. (b) **field-trip compliance** — `schoolops/field_trip.py` `create_field_trip_consent` (reuses `ConsentRequest` e-sign) + `build_medical_checklist` (confidential, offline-carryable, unmasked for teacher safety); tests 3/3. Both register rows `shipped`. Committed `0d3daf0b`.

**Wave E — Year-end governance (Phase 6). ✅ DONE 2026-06-07.** Built the **auditor magic-link**: operator mints a revocable, time-bounded `compliance.AuditorAccessGrant` (migration `0016`) → `TimestampSigner` magic link; the **public** `compliance:auditor_inspect` view needs no login (the signed, unexpired, unrevoked grant IS the auth), returns **only** PII-masked projections (`pii_masking.mask_student_for_auditor` → initials, birth-year, guardian withheld), and logs every view to `AuditorAccessLog`; staff console creates/lists/revokes. Tests `test_auditor_access` 6/6; gates register 7/7, migration drift clean, `check`/print/bare-except/**pii-logging** 0. **Now CLOSED 2026-06-07:** (a) **platform-wide non-repudiation** — `compliance.NonRepudiationLogEntry` (migration `0017`, per-school SHA-256 hash chain + HMAC server signature, append-only) + `non_repudiation.record_action/verify_chain` (any app; payload OR signature tamper detected) + `verify_non_repudiation_chain` command; tests 7/7. WebAuthn user-presence binds per-entry via `webauthn_presence` (client ceremony); write-once S3 Object Lock is a deploy-side mirror. (b) **state-reporting bridges** — `apps/reports/state_reporting.py` (GENERIC/US_EDFACTS/CA_CALPADS column maps + offline CSV) + `export_state_report` command; tests 5/5. Both register rows `shipped`. Committed `b09e529c`. (c) **geo-fence enforcement NOW CLOSED 2026-06-07** — `AuditorAccessGrant.ip_allowlist` (migration `0018`) + `auditor_access.ip_is_allowed` (stdlib `ipaddress`, CIDR-aware, **fail-closed**: a geo-fenced grant with an unplaceable client IP is denied); `auditor_inspect` rejects off-net IPs with 403 and records a denial (`AuditorAccessLog.allowed`/`denied_reason`); empty allowlist = opt-in/no restriction (backwards compatible); operator console accepts `ip_allowlist` on create + surfaces denied-view counts. Tests `test_auditor_access` 12/12 (+2 command). Committed `1c7f1784`, pushed.

**Wave F — Mesh sync deepening (cross-cutting). ✅ DONE 2026-06-07.** Built **real, proven-convergent CRDTs** in `apps/sync_engine/crdt.py` — `LWWRegister` ordered by **(Lamport clock, replica_id)** (deterministic + causal, the deliberate opposite of the rejected wall-clock LWW), `GSet` union, `lamport_tick`; and `crdt_wallet.py` — a grow-only unique-op log with idempotent/commutative/associative union-merge, Decimal-safe balance, and **multi-terminal offline debit with honest overdraft *detection* at reconciliation** (overdraft is uncoordinatable offline per CAP — detected, not faked; online mode can reject locally). This is the correct home for Wave C's deferred multi-terminal wallet reservation. Proven convergent: `test_crdt` 13/13 + `verify_crdt_convergence` command. New register row `crdt-offline-convergence` `shipped`. Committed `3ee7bbd5`. The device-to-device **transport** (BLE/Wi-Fi-Direct) rides on top of this correctness layer; `rmc-lan-mule-sync.js` is the existing LAN transport. **Plan fully closed 2026-06-07: the last non-code item — geo-fence enforcement (IP allowlist) on the auditor link — is now shipped and pushed (`1c7f1784`); every plan deliverable is code-complete, tested, and on `origin/main`.**

Sequence rationale: A is near-free trust (claim what's built), B/C are highest owner-visible value, D/E close the lifecycle bookends, F is the deepest engineering and can run in parallel.

---

## 6. SOT updates made on 2026-06-07

1. **This file** (`docs/GLOCAL_SOVEREIGNTY_PLAN.md`) — new plan SOT.
2. **`docs/MARKETING_REDESIGN_DIRECTION.md`** — appended §8 logging the 2026-06-07 expanded paste's harmful PART 3 code (reject-list reaffirmed against the live architecture).
3. **`apps/schools/feature_gap_register.py`** — added the lifecycle rows referenced in §4 as honest `planned` / `in_progress` (no false `shipped` claims; CI proof-resolution gate respected).

---

## 7. Guardrails (durable)

- Do **not** create `apps/glocal_kernel` or `apps/teacher_automation`. They do not exist; every capability maps to a real app above.
- Do **not** add a DB-per-tenant router, a JWT-claim RLS policy, or any hardcoded DB credential/host. Tenancy = `School` + `app.current_school_id` RLS, env-driven `DATABASE_URL`.
- Do **not** apply `100dvh`/`overflow:hidden`/`edos-text-shield`/`user-scalable=no` or runtime inline-style mutation. See `MARKETING_REDESIGN_DIRECTION.md` §3/§7.
- "CRDT/mesh" work goes through `apps/sync_engine` with a real convergence strategy — never a wall-clock last-write-wins merger.
- No blind platform-wide sweep. Bounded waves, validate before adoption, flip register rows to `shipped` only on a resolving proof.
