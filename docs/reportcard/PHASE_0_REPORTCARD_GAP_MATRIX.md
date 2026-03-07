# Phase 0 Report Card Gap Matrix

## Source Mapping (From Provided Images)

- `Image A` (full marks grid with per-subject rows and class council block) is the **Term report** sample.
- `Image B` (lighter sheet with mostly term aggregate blocks) is the **Annual/consolidated** sample.
- `Image C` is the school **logo** source and must support watermark rendering.

## Current Capability Snapshot

- Term template exists in:
  - `templates/reports/term_report_cameroon.html`
  - `templates/reports/term_report_cameroon_modern.html`
- Annual template exists in:
  - `templates/reports/annual_report_cameroon.html`
  - `templates/reports/annual_report_cameroon_modern.html`
- Report style configuration already supports:
  - labels JSON (`ReportCardStyle.labels`)
  - layout JSON (`ReportCardStyle.layout_config`)
  - color tokens and CSS snippet

## Gaps Identified

1. **Builder IA/layout**
- Builder workflow currently sits in the right column below preview.
- Request is to place Builder workflow under Catalog + Assignment in left column.

2. **Live preview resiliency**
- Preview panel needs explicit in-panel error fallback (retry + open tab helper).

3. **Watermark configurability**
- No configurable watermark image pipeline in report styles.
- Logo appears in header but not as configurable watermark behavior.

4. **Term card field parity**
- Teacher name column is not fully mapped from data for all rows.
- Rank per subject row is not currently populated.
- Signature/persona blocks and discipline/council labels are not fully tokenized for all variants.
- Some top identity blocks (resumption/reprise, enrollment wording variants) are static or partially tokenized.

5. **Annual card field parity**
- Consolidated annual summary exists, but sample-specific section naming and block ordering are not fully aligned.
- Some annual-specific fields (term progression visual, annual council notes) need stronger layout_config flags.

6. **Operational state clarity**
- Builder page lacks a persistent "active style + last saved + unsaved draft" strip tied to edits.

## Phase 0 Decisions Locked

- Treat provided detailed sheet as canonical **Term** design reference.
- Treat sparse consolidated sheet as canonical **Annual** design reference.
- Add configurable watermark controls at both:
  - global default level (Site settings)
  - per-style override level (Report card style)
- Keep all report headings/labels configurable through labels/layout config and avoid hardcoded wording.

## Next Phase Execution Order

1. Builder IA refactor (move workflow under catalog/assignment).
2. Compact workflow state strip + unsaved changes guard.
3. Live preview fallback UX improvements.
4. Watermark model + migration + builder controls + preview integration.
5. Term/annual parity completion with configurable fields.
6. Tests expansion and release gate validation.

