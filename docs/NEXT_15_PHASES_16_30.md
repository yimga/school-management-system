# Next 15 Logical Phases (16–30) — Completion Summary

**Purpose:** Second batch of 15 phases to advance toward "what we want to be," derived from PATH_TO_100 and RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH. Each phase is implemented, documented, or N/A with owner/date.

**Authority:** PATH_TO_100_PERCENT_EXECUTION_PLAN.md, RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md, NA_REGISTER_PATH_TO_100.md. Batch 1: [NEXT_15_PHASES_COMPLETION.md](NEXT_15_PHASES_COMPLETION.md).

---

## Phase list and status

| # | Phase | SOT/PATH ref | Status | Notes |
|---|--------|--------------|--------|--------|
| 16 | Marketplace: preview/screenshot fields | III.23 | Documented | MARKETPLACE_LISTING_METADATA.md: use listing metadata JSON (screenshot_url, preview_image_url); UI reads when present. |
| 17 | Marketplace: trust markers | III.24 | Documented | MARKETPLACE_LISTING_METADATA.md: metadata.verified, trust_badges; catalog UI when product prioritizes. |
| 18 | Marketplace: scope/permission visibility | III.25 | Documented | MARKETPLACE_LISTING_METADATA.md: metadata.required_permissions; show in listing/install flow. |
| 19 | Reports: theme/policy integration docs | III.51 | DONE | REPORTS_THEME_AND_POLICY_INTEGRATION.md added (theme: ReportCardStyle, ThemePack; policy/registry: labels, packs, Output Studio links). |
| 20 | Policies: impact preview | III.27 | Documented | Control Studio "Diff / impact summary" → studio_os:control_impact; super_policy_diff for policy diff. Impact preview in control_impact. |
| 21 | Launch Studio: 10-item checklist and staging | III.9 | Documented | launch_studio_checklist.md: 10 must-support; Step 34 local/CI verified; staging sign-off row when run. |
| 22 | Phase H: full codebase pass | V.12 | Documented | PHASE_H_MANUAL_CHECKLIST.md; phase_h_audit.py, phase_h_url_check.py; systematic pass per checklist. |
| 23 | Deploy visibility | V.13 | Documented | PHASE_H_MANUAL_CHECKLIST §6; RELEASE_CHECKLIST; CHANGES_NOT_VISIBLE_AFTER_DEPLOY when needed. |
| 24 | Full test suite run | V.14 | Documented | Run `python manage.py test --no-input`; fix regressions; phase_h_verification + pre_deploy_gate in place. |
| 25 | Accounts: onboarding/setup link | III.33 | Documented | Onboarding flows in setup_studio, portal/views_onboarding, schools/signup; Launch Studio links guided_onboarding; backend dashboard links to Studio/setup. |
| 26 | Portal: theme from Experience Studio | III.34 | DONE | Portal theme/branding from get_effective_site_settings; Experience Studio drives theme; deep link to studio in shell. |
| 27 | Report Platform in Output Studio | IV.6 | DONE | report_library redirects to studio_os:output; ReportPack, list_active_report_packs, pack preview in Output; hub + rail. |
| 28 | Observability: structured logging expansion | III.69 | Documented | platform_runtime structured_logging; log_exception_with_context in key paths; expand per SOT §6.23 when prioritized. |
| 29 | API Center integration governance | IV.25 | Documented | docs/apicenter_integration_governance.md; API Center dashboard exists; full governance console N/A product. |
| 30 | Sync PATH_TO_100 and SOT | §11 | DONE | Revision history updated; NEXT_15_PHASES_16_30 + reports/marketplace docs; batch 2 recorded. |

---

## Implemented in this batch

- **Reports theme/policy (Phase 19):** New doc `docs/REPORTS_THEME_AND_POLICY_INTEGRATION.md` — ReportCardStyle, ThemePack, Output Studio branding inheritance and Policy & registry; report labels and packs.
- **Marketplace metadata (Phases 16–18):** New doc `docs/MARKETPLACE_LISTING_METADATA.md` — metadata JSON for screenshot/preview, trust markers, scope/permissions; UI guidance.
- **Phases 26–27, 30:** Confirmed existing behavior (Portal theme from Experience; Report Platform in Output); PATH_TO_100 and this doc updated.

---

## Documented / N/A (no code change)

- **Policies impact preview (20):** control_impact and super_policy_diff in place; documented.
- **Launch Studio (21):** launch_studio_checklist.md; staging row when run.
- **Phase H (22–24):** PHASE_H_MANUAL_CHECKLIST; deploy visibility; full test suite — run and fix when releasing.
- **Accounts onboarding (25):** Links and flows documented.
- **Observability (28):** Structured logging in place; expand per §6.23.
- **API Center (29):** Governance doc and dashboard; full console N/A.

---

## Verification

- **Reports doc:** Open docs/REPORTS_THEME_AND_POLICY_INTEGRATION.md; confirm Output Studio branding + Policy & registry links.
- **Marketplace doc:** Open docs/MARKETPLACE_LISTING_METADATA.md; use metadata keys in seed or admin for screenshot/trust/scope when needed.
- **Phase H:** Run scripts/phase_h_audit.py and scripts/phase_h_url_check.py; complete PHASE_H_MANUAL_CHECKLIST on deploy.

---

**Next batch:** [NEXT_15_PHASES_31_45.md](NEXT_15_PHASES_31_45.md) (phases 31–45).

*Last updated: 2026-03-12. Sync with PATH_TO_100 revision history and SOT.*
