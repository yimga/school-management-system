# Reports: Theme and Policy Integration (III.51)

**Purpose:** Document how reports use theme (ReportCardStyle, theme packs) and policy/registry so III.51 is verifiable. See [PATH_TO_100_PERCENT_EXECUTION_PLAN.md](PATH_TO_100_PERCENT_EXECUTION_PLAN.md) §6.19, [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §5.3.

---

## Theme integration

- **ReportCardStyle:** Reports use `ReportCardStyle` for colors, labels, layout (primary_color, accent_color, header/footer, watermark). Assignment at classroom or site level; SITE fallback for primary/accent.
- **ThemePack:** Site theme (ThemePack) drives portal and backend; report styles can inherit semantic colors from theme where configured (THEME_CONSOLIDATION_AND_IMPROVEMENTS.md).
- **Output Studio:** "Branding inheritance" (studio_os:output_branding_inheritance) explains how reports/documents inherit theme (primary, logo); links to Theme & colors.
- **Live preview:** reportcard_style_live_preview; theme_colors.html live preview for theme changes that affect reports.

## Policy / registry integration

- **Report labels:** `resolve_report_labels`, `GLOBAL_REPORT_LABELS`; policy and region can drive label overrides (e.g. term labels, region display).
- **Report packs:** ReportPack in use; list_active_report_packs, build_report_pack_preview, normalize_report_pack_dependencies. Output Studio "Policy & registry" (studio_os:output_policy_registry) explains report packs vs policy (blueprints) and metadata lineage.
- **Registry:** Report types and pack metadata are catalogued; lineage and governance in metadata app. No separate "report types registry" model; report packs and ReportCardStyle catalog serve as registry surface.

## Verification

- Output Studio → Report library (or redirect) shows pack preview and dependencies.
- Output Studio rail → "Branding inheritance" and "Policy & registry" describe theme and policy/registry integration.
- Report generation uses get_effective_site_settings / ReportCardStyle and region-aware labels.

---

*SOT ref: §6.19 III.51; PATH_TO_100 III.51.*
