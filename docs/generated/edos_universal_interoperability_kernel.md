# EdOS Universal Interoperability and Global Transfer Kernel

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_INTEROP_KERNEL_READY`

## Scope

Re-architects global_registries + interop + metadata + people + student360 + academics + finance + migration_cloud around the Linux-style open educational data layer: immutable canonical core schemas, custom-field-to-global-type mapping, secure transfer envelopes for student/teacher/alumni, academic history portability, enrollment portability, finance summary portability where legal, guardian/custody portability where legal, consent/legal gate, audit event, formal-school/private-academy dual-profile model, government/MoE export envelope, NGO anonymized impact envelope.

## Sections

### Canonical global field classes (13 — already shipped in Prompt 1 Phase 7)

- identity — unique_id + verified_identity_hash
- demographic — birthdate (date_of_birth), gender (gender_self_id), nationality_iso2
- contact — primary_email + primary_phone_e164 + redaction_class
- enrollment — current_school_id + grade_level + status + last_enrollment_change_at
- guardian/custody — guardians[] {id, relationship, legal_custody_flag, communication_consent}
- academic record — grades[] {term, subject, score, scale_id, attestation_hash}
- attendance — attendance_summary {present_days, absent_days, late_days, hash_proof}
- finance summary — outstanding_balance_minor_units + currency_iso3 + last_settled_at (legal-gated)
- medical/safeguarding flags — encrypted_blob_pointer + access_audit_required (legal-gated)
- compliance status — consents[] {policy_id, granted_at, jurisdiction}
- consent/legal permissions — permissions[] {scope, granted_by_role, expiry_at}
- curriculum track — track_id + framework_id (CBSE/IGCSE/IB/Bac/...)
- academy/private tutoring dimension — academy_profile {tutoring_subjects, hourly_rate_minor_units}

### Transfer envelopes (signed + auditable)

- Student transfer envelope — apps.interop.student_transfer_envelope.py with HMAC-SHA512 signature + consent gate
- Teacher transfer envelope — apps.interop.teacher_transfer_envelope.py
- Alumni transfer envelope — apps.interop.alumni_transfer_envelope.py (legal-gated for jurisdictions allowing alumni data sharing)
- Government/MoE export envelope — anonymized + jurisdiction-tagged + auditable
- NGO donor impact envelope — anonymized aggregate; NO student PII

### Dual-identity profile (formal school + private academy)

- Single canonical Person with dual profile slots: school_enrollment_profile + academy_tutoring_profile
- Identity ledger — apps.student360.dual_identity_profile_contract enforces shared verified_identity_hash; no profile drift
- Cross-context query API — apps.interop returns merged record gated by consent

## Repo evidence (anchor paths)

- `apps/global_registries/`
- `apps/interop/`
- `apps/metadata/`
- `apps/people/`
- `apps/student360/`
- `apps/academics/`
- `apps/finance/`
- `apps/migration_cloud/`

## Tests

- `apps/interop/tests/test_edos_student_transfer_envelope_v2.py`
- `apps/interop/tests/test_edos_teacher_transfer_envelope_v2.py`
- `apps/student360/tests/test_edos_dual_identity_profile_v2.py`

## External blockers (deferred — repo cannot fix)

- live PSP settlement reconciliation per corridor
- SOC2 Type II PDF
- MoE / Ministry of Education per-country live integrations
- WhatsApp Business platform Meta verification
- USSD telecom partner agreements per country
- native push notification wrapper (Capacitor/Tauri) — deferred until first-100-schools proof
- live LiteLLM API keys on Render
- Render SHA parity live verification
- multi-corridor pilot ingestion
- Postgres RLS enforced in production (current local env is SQLite)

## PWA-first posture

PWA is the launch mobile strategy. Native iOS/Android apps are explicitly DEFERRED until web core stability + first-100-schools proof + PWA installability proof. Service worker + manifest + IndexedDB + offline queue shipped in prior batches; this re-architecture preserves and consumes that infrastructure rather than forking.

## Honesty notes

- Repo-scope contracts only — no live vendor integration claims.
- Existing canonical models preserved; metadata layer absorbs tenant variance per architecture correction.
- External blockers listed above remain unchanged by batch 1489.
