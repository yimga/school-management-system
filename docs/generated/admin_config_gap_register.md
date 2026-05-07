# Admin Configuration Gap Register

| Gap | Classification | Severity | Risk | Recommended fix | Status |
|---|---|---|---|---|---|
| Tenant `/school` product aliases were incomplete | closed | high | Product navigation could remain scattered instead of following the clean school control model | Add `/school/apps/`, `/school/billing/`, `/school/money/`, `/school/workflows/`, `/school/offline/`, `/school/audit/`, `/school/security/` aliases to existing tenant-safe surfaces | fixed |
| Dedicated tenant dashboard/policy/metadata detail pages are aliases or tenant-equivalent routes | planned_depth | medium | UX depth may be less direct than ideal information architecture | Add explicit pages only when product requirements need more than current tenant-safe surfaces | not critical |
| App Catalog monetization/settlement cannot be marked live-ready | partial_external_blocker | high | Fake payment readiness would mislead operators and buyers | Keep billing truth `external_required` until live provider proof exists | blocked by external proof |
| PSP/payment provider live readiness remains external_required | partial_external_blocker | high | Revenue collection/settlement claims could be overstated | Require live PSP verification evidence before changing readiness labels | blocked by external proof |
| Some `/configuration` detail pages are facades over existing systems | planned_depth | low | Operators may need one extra click to the owning surface | Keep facade links proof-backed; deepen only concrete workflows | accepted |
| SOT/log update not made during initial partial audit pass | closed | low | SOT may not cite these new generated artifacts yet | Update SOT/log only after tests and verifiers pass | fixed |

Critical repo gaps after fix: none.
