"""Universal Migration Cloud — end-to-end pipeline (Phases U1 → U9 + v2.7/v2.8 polish).

Public surfaces, in lifecycle order::

    BundleIngestionService.ingest(spec)        → PENDING / INGESTING
    pipeline.advance_bundle(bundle_id)         → PROFILED / CLASSIFIED / MAPPED
    orchestrator.apply_bundle(bundle_id)       → APPLYING / APPLIED
    reconciliation.reconcile_bundle(id, ...)   → RECONCILED  (cohort= for subset)
    shadow.start_shadow_window(bundle_id, ...) → opens parallel-run window
    shadow.refresh_shadow(bundle_id, ...)      → ticks drift; auto-cutover if armed
    shadow.close_shadow(bundle_id, accepted=)  → seal + (optional) → RECONCILED

The promise: any school can hand us anything they have — zip, folder,
SQL dump, SQLite, .mdb/.accdb, PDF transcripts (with OCR fallback),
Google Drive / OneDrive / Dropbox folders, URL, SFTP, S3, emailed
attachments — and the pipeline lands every artifact under one
``MigrationBundle`` without the operator naming the source up front.

Source-specific accelerators (PowerSchool, Blackbaud, Veracross, FACTS,
Skyward, Alma, OneRoster + 24 regional vendors) ride the same pipeline.
They never bypass the universal mapper for non-pre-mapped columns —
fallback to universal is the safety net under every accelerator.

Global coverage (v2.7): 39 countries × 41 grading scales × 25 language
synonym overlays × 6 attendance dialects. Country hint surfaces from
``school.country_code`` into every transformer's locale hints.

Trust layer (v2.8): shadow-mode runs old-SIS counts vs new-tenant counts
in parallel, computes symmetric drift, auto-cutovers after 3 sustained
clean ticks when armed. State persists in
``MigrationBundle.reconciliation_summary['shadow']``.

For architecture see ``docs/MIGRATION_UNIVERSAL_INTAKE.md``.
For AI usage see ``docs/MIGRATION_CLOUD_AI.md``.
For real-world walkthroughs see ``docs/MIGRATION_CLOUD_SCENARIOS.md``.
"""
