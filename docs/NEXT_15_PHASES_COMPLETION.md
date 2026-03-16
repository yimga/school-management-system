# Next 15 Logical Phases — Completion Summary

**Purpose:** Advance toward "what we want to be" by executing the next 15 logical phases derived from PATH_TO_100 and RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH. Each phase is either implemented, documented, or explicitly N/A with owner/date.

**Authority:** PATH_TO_100_PERCENT_EXECUTION_PLAN.md, RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md, NA_REGISTER_PATH_TO_100.md.

---

## Phase list and status

| # | Phase | SOT/PATH ref | Status | Notes |
|---|--------|--------------|--------|--------|
| 1 | Domain ownership / brand_experience next batch | §6.6 | Documented | Next-batch scope in domain_ownership; absorb ownership N/A (product 2026-03-12). |
| 2 | Global registries in setup payload / recommendations | III.20 | DONE | setup_studio get_setup_studio_payload uses migration_path_flow, blueprint_rankings; registries referenced in docs. |
| 3 | Richer marketplace listing metadata | III.22 | DONE | Description, categories, region/plan compatibility in marketplace listing. |
| 4 | Report library: list/filter by ReportPack | III.48 | DONE | report_library redirects to Output Studio; ReportPack in use; list_active_report_packs, pack preview, dependencies. |
| 5 | Document library: filter by pack | III.34/III.35 | DONE | document_library_manage filters by pack (document_pack__code); lifecycle, search; redirect to Output when not embed. |
| 6 | Policy diff: clear link from Control Studio | III.26 | DONE | Control Studio rail: "Policy diff" link added (super:policy_diff) after "Blueprints & policy packs". |
| 7 | Portal → Output Studio deep link | III.35 | DONE | Document library (non-embed) redirects to studio_os:output?pane=documents; embed shows "Open in Output Studio". |
| 8 | Academics: 1–2 critical-path tests | III.39 | DONE | apps/academics/tests/test_academics_critical_paths.py: get_active_year_and_term (2), teacher_syllabus_hub (2). |
| 9 | Feature control: owner/expiry in ledger | §5.2 / IV.5 | Documented | feature_control_ledger.md; FeatureToggleState has expires_at, updated_by; definition metadata for owner/source. |
| 10 | Full test suite run and fix critical failures | V.14 | In progress | Run full suite; fix regressions; document in revision history. |
| 11 | Launch checklist: verify III.9 / Launch Studio | III.9 | Documented | launch_studio_checklist.md 10 items; completion gate and staging verification open. |
| 12 | Registry UI link from Control | III.21 | DONE | Control Studio rail has "Lineage & registry" (metadata:metadata_lineage_graph); registry visibility in Control. |
| 13 | Reports: theme/policy integration docs | III.51 | Documented | Reports use theme (ReportCardStyle, theme packs) and policy; doc in report packs / Output Studio. |
| 14 | Observability: runtime resolution logging | III.67/69 | Documented | platform_runtime tracing; structured logging in place; expand per SOT §6.23. |
| 15 | Sync PATH_TO_100 and SOT (mark done/N/A, revision) | §11 | DONE | Revision history updated; Policy diff link, academics tests, NEXT_15 doc added. |

---

## Implemented in this batch

- **Control Studio → Policy diff:** In `apps/studio_os/views.py`, control_left_rail now includes "Policy diff" → `super:policy_diff?embed=1` after "Blueprints & policy packs".
- **Academics critical-path tests:** New file `apps/academics/tests/test_academics_critical_paths.py`:
  - `GetActiveYearAndTermTests`: returns (None, None) when no data; returns (year, term) when configured with school.
  - `SyllabusHubCriticalPathTests`: 403 without TeacherProfile; 200 with TeacherProfile and hub context (cards, year_term).
- **Document library:** Already filters by pack (pack=), lifecycle, search; non-embed redirects to Output Studio documents pane.
- **Report library:** Redirects to studio_os:output; ReportPack and list_active_report_packs in use; filter by pack in Output Studio.
- **Registry UI:** Control Studio rail already has "Lineage & registry" (metadata_lineage_graph).

---

## Documented / N/A (no code change this batch)

- **Domain ownership next batch:** See domain_ownership.md; absorb ownership N/A (product).
- **Feature control owner/expiry:** feature_control_ledger.md; models already have expires_at (FeatureToggleState), updated_by; metadata on definition for owner/source (IV.5 incremental).
- **Launch Studio:** launch_studio_checklist.md; III.9 completion gate and staging verification when product prioritizes.
- **Reports theme/policy:** Existing integration; further docs in report packs / Output Studio.
- **Observability:** platform_runtime tracing and structured logging; expand per §6.23 when prioritized.

---

## Verification

- **Policy diff link:** Visit Studio OS → Control → left rail → "Policy diff" → super_policy_diff page.
- **Academics tests:** `python manage.py test apps.academics.tests.test_academics_critical_paths --no-input`
- **Report/Document:** Report library URL → redirects to Output; Document library (portal) without embed → redirects to Output?pane=documents.

---

**Next batch:** [NEXT_15_PHASES_16_30.md](NEXT_15_PHASES_16_30.md) (phases 16–30).

*Last updated: 2026-03-12. Sync with PATH_TO_100 revision history and SOT.*
