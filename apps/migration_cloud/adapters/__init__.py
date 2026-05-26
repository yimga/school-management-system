"""Wave Q6 (v3.95.2 — 2026-05-26) — Per-source migration adapter package.

Each module here implements a read-only migration adapter for a specific
SIS source. Adapters convert vendor-specific export formats to the canonical
RMC ingestion shape.

Write-back paths to source systems remain counsel-blocked; see the
``honest-stub`` markers in ``companion-docker/app/extractors/`` and the
verifier ``scripts/verify_honest_stubs_intact.py``.
"""
