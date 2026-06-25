# Offline-first: the two-rail architecture (SOT)

RunMyCampus runs **two** offline write rails. They coexist by design — but they
are easy to confuse, and a partial reading of one rail makes the platform look
far less offline-capable than it is. This document is the canonical map so no
future audit (human or agent) repeats that mistake.

> **TL;DR** — A declared offline capability is *honest* only when a **client
> producer** queues it AND a **server applier** writes it, on **at least one**
> rail. The CI gate `scripts/verify_offline_capability_implementation.py`
> enforces exactly this, across both rails.

---

## Rail 1 — SODP / OfflineAction (typed-intent rail)

The older, broad rail. Clients enqueue **typed intents** that the server drains
and applies.

| Layer | Location |
|-------|----------|
| Client producers | `static/js/rmc-offline-portal-forms.js` (binds `form[data-rmc-offline-form="<kind>"]`) → `window.rmcOfflineEnqueue` (`static/js/offline-queue-client.js`) |
| Wire contract | `{ action_type, payload, idempotency_key }` |
| Type registry | `apps/platform_runtime/offline_action_types.py` (`OfflineActionType` + `LEGACY_TO_SODP`) |
| Validation | `offline_action_types.validate_offline_payload()` |
| Server appliers | `apps/platform_runtime/offline_queue.py` → `_apply_payload()` dispatch → `_apply_<x>()` |
| Persistence | model writes, or `School.settings` buckets (e.g. homework via `lesson_homework_kernel`) |

**Covers:** attendance, grades, **homework**, payment-receipt capture, student
notes, support tickets, donations, generic field-capture, parent/staff notify.

## Rail 2 — WAL stream (zero-latency rail, v4)

The newer, low-latency rail. Clients append to an IndexedDB write-ahead log; a
Celery drainer applies envelopes under `rls_school` context.

| Layer | Location |
|-------|----------|
| Client producers | `static/js/rmc-wal-stream.js` (`window.rmcWAL.append`) + page enhancers (`_pages/rmc-attendance-wal-enhance.js`, `_pages/rmc-gradebook-wal-enhance.js`, `rmc-message-outbox.js`) |
| Consumer allow-list | `apps/wal_stream/consumers.py` `_ALLOWED_DOMAINS` |
| Server appliers | `apps/wal_stream/writers.py` `_REGISTRY` (one `_apply_<domain>` per domain) |

**Covers:** attendance, teacher_attendance, grade, communication_send,
thread_message_create, announcement_create, audit_event.

**Deliberately NOT on the WAL rail:** `billing_charge`. A previous WAL money
writer silently lost funds (wrong model contract) and was removed
(`writers.py:487-496`). Money capture stays on the SODP rail as
`payment_receipt` (receipt details queue offline; the *file* upload defers to
reconnect — an honest online-only boundary, not theater).

---

## Capability → rail map (the contract the gate enforces)

| Manifest capability (`OFFLINE_QUEUED_WRITE`) | SODP intent | WAL domain | Status |
|----------------------------------------------|-------------|-----------|--------|
| `enable_offline_form_queue` | generic `rmcOfflineEnqueue` | — | real |
| `enable_offline_attendance_sync` | `attendance` / `attendance.mark` | `attendance`, `teacher_attendance` | real (both rails) |
| `enable_offline_grade_sync` | `grading` / `grade.submit` | `grade` | real (both rails) |
| `enable_offline_homework_sync` | `homework_submission` / `homework.submit` | — | **producer + applier real, UI surface latent** |

### The one latent capability — homework

Homework offline is fully built on the SODP rail: producer
(`rmc-offline-portal-forms.js::wireHomeworkSubmission`), validation, server
applier (`offline_queue.py::_apply_homework_submission`), and a passing test
(`apps/platform_runtime/tests/test_offline_queue.py::test_homework_submission_offline_queues_and_syncs`).

It is **latent**, not theater: no template currently carries
`data-rmc-offline-form="homework_submission"`, so the producer binds to nothing
and a user cannot trigger it. Closing this is a *product* task — ship a student
homework-submission surface and tag its form — not a plumbing task. The gate
reports it as `latent` (non-fatal) until that UI lands.

---

## Why the gate exists

The pre-existing `verify_offline_manifest_taxonomy.py` proves a manifest
*declares* capability flags with the right shape. It cannot prove any flag is
backed by code. `verify_offline_capability_implementation.py` adds the missing
half: it fails CI when a declared capability has no producer or no applier on
either rail, and it fails when a new `enable_offline_*` flag is added without a
mapped, implemented rail. That makes offline-first a runtime-enforced invariant
instead of a claim — and keeps the two rails from silently drifting apart.
