# EdOS Global-Local Localization and Sovereignty Layer

**Batch:** 1489 · **SW:** `sms-v3.86.0-edos-realm-rearchitecture-2026-05-24` · **Generated:** 2026-05-24T00:00:00+00:00

**Verdict:** `EDOS_GLOBAL_LOCAL_LAYER_READY`

## Scope

Re-architects locale + global_registries + compliance + siteconfig + brand_experience + metadata + finance + communication + academics + reports + sync_engine + platform_runtime to expose a single Local Overlay service. Builds on the existing 250 ISO2 regional payment profile registry + 25 LocalExperienceProfile + 98-template marketplace + 51-market testimonial voice + per-state India calendar variants + script-aware UI.

## Sections

### Local overlay primitives

- Local terminology mapper — apps.locale lexicon cascade (52 templates currently using {% term %} + {% blocktrans asvar %})
- School-type mapper — IN/CM/PK/MY/PH dual-system overlays + ZA AF Provincial + CH 4 cantons + BE 3 communities
- Academic calendar mapper — IN 3-variant per-state + IN_per-language overlay (KN/ML/MR/OR/TA/TE/GU/HI/PA/UR/CBSE)
- Grading system mapper — multi-curriculum (IGCSE/IB/Bac/GCE/CBSE/ICSE/state boards) matrix
- Regional compliance map — GDPR/UK-GDPR/CCPA/POPIA/LGPD/PDPB/PIPEDA per ISO2
- Data residency policy map — EU/UK/CA/AU/AE/IN/BR/ZA/KE/NG residency target per tenant
- Local profile map — 25 LocalExperienceProfile (CM/NG/GH/KE/ZA/CI/SN/MA/IN-CBSE/IN-KA/PK/BD/JP/KR/CN/PH/MY/ID/US/GB/AU/AE/MX/BR + extensions)
- Local template selection — 75 templates baseline + 50 local-first + 23 specialized = 98 total templates
- RTL posture — Arabic/Hebrew + script-aware UI layout engine
- Language override posture — 51 of 51 voice-dict markets covered (100%)
- Country/region feature matrix — 250 ISO2 with regional payment profiles
- Script-aware UI layout engine — apps.brand_experience palette + CSS bundle responsive at 390/768/1366 breakpoints
- Flexbox-isomorphic typographic layout posture — design-tokens-local-palettes.css with 10 heritage families
- Right-to-disconnect rules — apps.communication availability_guard + out-of-hours queue
- GDPR anonymization/key-shredding contract — apps.compliance erasure_request workflow
- Data sovereignty provisioning posture — Render region tag per tenant (contract; live cross-region NOT shipped)
- Local payment rail matrix — 13 PSP rail registry entries + 250 ISO2 profiles
- PWA low-data defaults by region — CountryRegistry.cockpit_payload.low_bandwidth_class per ISO2

### Sovereignty honest posture

- Repo-scope policy maps SHIPPED — DEFERRED: live cross-region physical sharding (Render multi-region + paid tier ops work).
- Data residency CONTRACTED — DEFERRED: per-country live verification pilots.
- Live MoE/government export TARGETS DOCUMENTED — DEFERRED: per-country MoE integration agreements.

## Repo evidence (anchor paths)

- `apps/locale/`
- `apps/global_registries/`
- `apps/compliance/`
- `apps/siteconfig/local_experience_profiles.py`
- `apps/siteconfig/country_registry.py`
- `apps/brand_experience/`
- `apps/metadata/`
- `apps/finance/regional_payment_profiles.py`
- `apps/communication/`
- `apps/academics/`
- `apps/reports/`
- `apps/sync_engine/`
- `apps/platform_runtime/`
- `static/css/design-tokens-local-palettes.css`

## Tests

- `apps/locale/tests/test_edos_local_overlay_resolution.py`
- `apps/compliance/tests/test_edos_data_residency_contract.py`
- `apps/siteconfig/tests/test_edos_country_registry_overlay.py`

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
