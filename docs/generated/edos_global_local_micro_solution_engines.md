# EdOS Global-Local Micro-Solution Engines

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_GLOBAL_LOCAL_MICRO_ENGINES_READY`

## Scope

Re-architects the platform to support low-cost local solutions across LATAM, Africa, APAC/South Asia, Europe/UK, and MENA. Each region is a contract registry + adapter set + workflow + tests. NO fake live government/PSP/telecom integrations.

## Sections

### LATAM adapter set

- Fiscal router — apps.finance.fiscal_router_latam (Brazil Nota Fiscal, Mexico CFDI, Chile DTE, Argentina CAE)
- Electronic invoice contract — apps.finance.einvoice_latam_contract
- Cash barcode voucher — Boleto/OXXO/PagoFácil voucher network contract
- Pix/CoDi/Transbank — PSP adapter contracts
- WhatsApp receipt delivery — apps.communication.whatsapp_receipt_contract (Meta verification blocker preserved)

### Africa adapter set

- Mobile money split-wallet — apps.finance.mobile_money_split_wallet (M-Pesa, MoMo, Orange Money)
- USSD payment — apps.communication.ussd_payment_adapter
- Offline mobile money webhook — apps.finance.offline_mobile_money_webhook
- P2P offline sync — apps.sync_engine.p2p_sync_contract
- School-in-a-Box edge kernel — apps.sync_engine.school_in_a_box_kernel_contract
- Shared-device teacher PWA — apps.accounts.shared_device_profile_contract
- Low-data parent messaging — apps.communication low_data_fallback_contract

### APAC adapter set

- Dual identity formal school / private academy — apps.student360.dual_identity_profile_contract
- Script-aware UI engine — apps.brand_experience script_aware_layout (CJK/Arabic/Hebrew/Hindi/Bengali/Tamil/Telugu/Khmer/Burmese/Lao/Sinhala/Thai)
- Shared-device portal — apps.accounts.shared_device_profile_contract
- Automated state compliance export — apps.compliance.state_compliance_export per IN-state/PK-province
- Tutoring marketplace posture — apps.marketplace.tutoring_marketplace_contract

### Europe / UK adapter set

- Cryptographic anonymization/key-shredding — apps.compliance.erasure_request workflow
- Right-to-disconnect communication buffer — apps.communication.out_of_hours_queue
- Labor-hours policy enforcement — apps.communication.right_to_disconnect_policy
- Data preservation/anonymization model — apps.compliance.gdpr_data_model

### MENA adapter set

- Data residency provisioning — apps.siteconfig.data_residency_provisioning (Render multi-region external blocker preserved)
- Multi-curriculum grading matrix — apps.academics.curriculum_matrix (Bac D, GCE A/L, national curricula)
- Arabic/RTL support — apps.brand_experience RTL_layout + apps.locale Arabic lexicon
- National curriculum overlays — apps.academics.national_curriculum_overlay per ISO2

## Repo evidence (anchor paths)

- `apps/finance/`
- `apps/communication/`
- `apps/sync_engine/`
- `apps/accounts/`
- `apps/student360/`
- `apps/brand_experience/`
- `apps/compliance/`
- `apps/locale/`
- `apps/academics/`
- `apps/marketplace/`

## Tests

- `apps/finance/tests/test_edos_latam_fiscal_router.py`
- `apps/finance/tests/test_edos_africa_mobile_money_split.py`
- `apps/communication/tests/test_edos_apac_script_aware_messaging.py`
- `apps/compliance/tests/test_edos_europe_right_to_disconnect.py`
- `apps/academics/tests/test_edos_mena_curriculum_matrix.py`

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
