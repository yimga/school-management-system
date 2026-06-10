# Local-First / Global / Offline — Chain-Reaction Truth Audit

Date: 2026-06-10
Branch: main
Method: direct read of the live repo (not a zip snapshot). Every claim below points to a
file + line-level fact I verified; nothing is assumed.

---

## 0. Verdict (one line)

The local-first / global / offline **foundation is real and the country→localization half of
the chain is genuinely wired**. The **manifest spine is built, tested — and orphaned**: nothing
in the live product calls it. That single disconnection, not "missing systems," is why the
chain reaction is unproven.

```
FOUNDATION (offline/PWA/sync code) ............ STRONG, REAL
COUNTRY BREADTH (catalogs, ISO, governance) ... STRONG, REAL
COUNTRY → LOCALIZATION WIRING ................. REAL (10+ production callers)
TENANT MANIFEST COMPILER ...................... BUILT + TESTED but ORPHANED (0 prod callers)
COUNTRY "PACK" AS A UNIFIED FACADE ............ DOES NOT EXIST (logic is scattered, by design)
CHAIN-REACTION END-TO-END ..................... UNPROVEN — broken at the manifest hand-off
CHAIN/OFFLINE VERIFIERS ....................... ALREADY EXIST (6), do not rebuild
```

---

## 1. What the external audit got RIGHT (confirmed against live code)

Every file the external audit named exists. This audit is grounded, unlike prior pastes.

| File | Lines | Status |
|---|---|---|
| `apps/siteconfig/_seed_country_localization.py` | 16,897 | real seed data |
| `apps/siteconfig/country_localization_service.py` | 1,060 | real, **wired** (§3) |
| `apps/siteconfig/country_experience_baselines.py` | 96 | real |
| `apps/sync_engine/tenant_manifest_compiler.py` | 147 | real, **orphaned** (§2) |
| `apps/platform_runtime/offline_queue.py` | 1,216 | real |
| `apps/platform_runtime/offline_mode_bundle.py` | 162 | real |
| `apps/platform_runtime/offline_workflow_apply.py` | 365 | real |
| `apps/api/offline_replay_views.py` | 384 | real |
| `apps/communication/offline_conflict_kernel.py` | 281 | real but ORPHANED → **RETIRED** (§9) |
| `apps/finance/payment_local_global_contract.py` | 388 | real |
| `apps/finance/country_readiness_register.py` | 431 | real |
| `apps/interop/transfer_envelope.py` | 155 | real |
| `apps/global_registries/schema_mapping.py` | 193 | real |
| `apps/migration_cloud/country_profiles.py` | 580 | real |

So: **"FOUNDATION STRONG, COUNTRY BREADTH STRONG, OFFLINE PRESENCE STRONG" is true.**
6 offline/PWA E2E specs also exist (`pwa-offline`, `offline-sync`, `offline-queue-replay`,
`offline-outbox-encryption`, `world-globe-online-offline`).

---

## 2. The decisive finding: the tenant manifest is ORPHANED

`apps/sync_engine/tenant_manifest_compiler.py::compile_manifest` emits **8 offline-sync fields
only**: `tenant_id_hash, schema_version, routes_allowlist, data_policies, pwa_cache_hints,
locale_default, feature_flags, checksum, signature_posture`. It carries **none** of the
"operating manifest" identity the vision describes (country, school_type, currency,
academic_year_model, grading_system, payment/comms contracts, lifecycle, health).

More important than narrowness: **it has zero production callers.**

- `grep tenant_manifest_compiler` across `apps/ services/ config/ ai/` (excluding its own file,
  tests, and `docs/generated/`) → **nothing**.
- The only `compile_manifest` call in `apps/setup_studio/wizard_resolvers.py:202` resolves to a
  **different** function — `apps.brand_experience.pwa_manifest.compile_manifest` (PWA branding),
  not the sync_engine one.
- The sync_engine compiler is referenced only by 3 test files and ~15 `docs/generated/*.json`
  proof artifacts.

**This is why the chain reaction is "unproven": the spine the vision hangs everything on is a
well-tested island that the live setup/offline path never invokes.** The external audit called
this "PARTIAL"; the truth is sharper — it is *disconnected*, and that is the actionable gap.

---

## 3. The half that IS wired (the strong half)

`country_localization_service` (1,060 lines) has **10+ production callers**, e.g.:
`schools/signup_views.py`, `lifecycle/views_rapid_create.py`, `siteconfig/context_processors.py`,
`governance/academic_pack_bridge.py`, `migration_cloud/signup_locale_bridge.py`,
`schools/marketing_geo_context.py`. So **country profile → localization → signup/setup context
is real and connected.** The chain is not imaginary; it is broken specifically at the
*localization → manifest → offline* hand-off, downstream of where the wiring currently ends.

Caveat found in the same file: `wizard_resolvers.list_grading_scales` returns a **flat hardcoded
list** (`gpa_4, gpa_5, percentage, …`), not a country-derived default — so even within the wizard,
"country → grading default" is breadth, not depth. (A scar comment at lines 224–229 documents a
prior bug where `list_countries` silently fell back to a hardcoded 31-country list — already fixed.)

---

## 4. What the external audit OVER-prescribes (sludge risk)

The 17-phase follow-up prompt would, if run verbatim:

1. **Re-create verifiers that already exist.** Live repo already has:
   `verify_local_first_completion.py`, `verify_local_first_surface_wiring.py`,
   `verify_sovereign_offline_depth.py`, `verify_sovereign_offline_foundation.py`,
   `verify_sovereign_offline_config_cascade.py`, `verify_sovereign_offline_e2e_scaffold.py`.
   Phase 11/14's "create a verifier if missing" is mostly redundant.
2. **Emit ~25 new `docs/generated/*.json|md` audit files** — the exact "proof sludge" the prompt's
   own rules forbid. `docs/generated/` already holds 328 local/offline/global docs.
3. **"Build country pack architecture" (Phase 2/6)** as if greenfield. There is no `CountryPack`
   class — but country logic is *deliberately* spread across localization_service +
   governance matrix + country_readiness_register + migration_cloud/country_profiles +
   experience_baselines. A facade may help, but it is a *consolidation*, not a missing system.

---

## 5. The real, minimal, high-leverage work (in priority order)

1. **Decide the manifest's fate, then wire or retire.** Either (a) make
   `country_localization_service` + `country_readiness_register` feed `compile_manifest` and have
   the setup/offline path actually consume the result, closing the one broken link; or (b) retire
   the orphaned compiler and its proof docs if the live PWA path already covers offline needs via
   `offline_mode_bundle`/`offline_queue`. Today it is schrödinger's-spine: tested but dead.
2. **Content, not architecture, is the country gap.** `apps/finance/data/regional_payment_profiles.json`
   is 15,100 lines but every country carries an identical 28-entry skeleton → ~94% placeholder
   (~15 real corridors). Real per-country payment/legal/calendar data needs external research and
   cannot be honestly fabricated. This is an **external proof gate**, not a repo task.
3. **If a CountryPack facade is wanted**, build it as a thin read-only resolver over the existing
   five sources — no new source of truth, no duplication.

---

## 6. External proof gates (cannot be closed in-repo, must not be claimed)

- Real payment-rail corridor data + provider contracts (M-Pesa, MTN MoMo, UPI, Paystack, …).
- Live SMS/WhatsApp/card/mobile-money provider delivery + settlement.
- Per-country legal/compliance/data-residency sign-off.
- Browser/PWA production offline proof on real devices/networks.

---

## 7. RESOLUTION (2026-06-10, same day) — the broken link is now wired

The orphan is connected. The chain `country profile → manifest → offline` now runs in the
live provisioning path, and the payment-content honesty is locked by CI.

**A. Manifest wired (new production caller).**
- New `apps/sync_engine/tenant_manifest_resolver.py::build_school_offline_manifest(school)` reads
  the school's country and enriches a manifest from the existing read-only registries:
  `locale_default` ← `country_localization_service.get_default_language`; country pack summary ←
  `resolve_country_pack`; HONEST payment posture ← `country_readiness_register.assess_country`;
  offline capability flags ← `offline_mode_bundle`.
- Wired into the **live path**: school provisioning → `maybe_apply_offline_bundle_on_provision`
  → `apply_offline_mode_bundle_for_school` (now resolves the manifest) →
  `apply_offline_mode_bundle_for_tenant` (now persists it under the `offline_tenant_manifest`
  backend flag). Best-effort: a resolution failure logs and never breaks provisioning.
- The sync_engine `compile_manifest` now has a real, non-test caller. Its deliberately-narrow
  field set is preserved (country/payment context rides in `data_policies`, respecting the
  scrub contract) — "Manifest 2.0" rich identity beyond offline needs is intentionally NOT added.

**B. Payment-content honesty locked (the real gap, closed the only honest way).**
- The ~235 placeholder corridors are NOT fabricated into real data (forbidden). Instead
  `scripts/verify_regional_payment_profiles_honesty.py` is a CI guard that FAILS if: a placeholder
  corridor ever resolves to a ready-implying tier; an unclassified rail token appears; a
  `config_only` corridor lacks a live PSP; or defined-corridor coverage regresses below the
  ratchet floor (15 today: BR CD CI CM EU GB GH KE NG RW SN TZ UG US ZA). Current state: clean
  (15 defined / 235 placeholder, 0 violations). Raising the floor celebrates new research.
- The manifest's payment posture flows through this honest register: a placeholder corridor is
  reported `live_collection=False, data_state="placeholder"` — the offline manifest can never tell
  a tenant a placeholder corridor collects money.

**Verification:** 8 new chain tests + 31 existing related tests green; `manage.py check` 0;
`makemigrations --check` no changes (no new models); honesty verifier exit 0. No SW bump (Python
only, no CSS/JS).

## 8. Closing verdict

```
LOCAL-FIRST GLOBAL OFFLINE — FOUNDATION READY (REPO SCOPE)
CHAIN-REACTION — PROVEN AT THE MANIFEST HAND-OFF (country → manifest → offline, live path + tests)
PAYMENT-CONTENT HONESTY — LOCKED BY CI (placeholders can never masquerade as ready)
COUNTRY DEPTH — EXTERNAL PROOF GATES REMAIN (real corridor data + legal + providers — not fabricable)
```

## 9. RETIREMENT (2026-06-10) — the one orphan the deeper audit found, removed

A second, rigorous "nothing-faked" sweep of the whole offline chain confirmed every
runtime module (`offline_queue`, `offline_workflow_apply`, `offline_replay_views`,
`offline_mode_bundle`, all `sync_engine/*`, the service worker, the PWA manifest) is
REAL and has live production callers — with **one** exception:

`apps/communication/offline_conflict_kernel.py` (shipped v3.96.1 Wave S-E, 2026-05-26,
with 19 tests) had **zero production callers**. It was a newer, richer, but never-wired
parallel conflict resolver: it used **raw wall-clock `LATER_WINS`** and a generic
`_merge_non_conflicting_fields` payload merge. The live, wired path
(`apps/sync_engine/conflict_resolver.py`, called at `offline_queue.py:704`) had already
moved past that — it resolves on **causal HLC logical clocks** ("never a raw wall-clock
race") and *deliberately* routes `FIELD_MERGE` to manual review ("requires a typed
domain handler"), rejecting exactly the generic merge the kernel performed.

So the kernel was not lost capability — it was an unadopted alternative that contradicts
the canonical design. **Retired** (owner-approved): deleted the module + its test
(`test_offline_conflict_kernel.py`) and removed its entry from
`scripts/verify_sync_semantics.py`'s run list. Conflict resolution is unchanged in
production (still the causal-clock resolver). The v3.96.1 service-worker changelog
comment is left intact as an accurate historical record of what once shipped.

```
OFFLINE CHAIN ORPHANS — 0 (was 1; offline_conflict_kernel retired, not a functional hole)
```
