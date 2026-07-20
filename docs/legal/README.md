# Legal / counsel artifacts (not fabricated)

This directory holds **externally produced** counsel documents. Agents and
operators must **never** invent a signoff PDF or letterhead attestation.

## Required before MAA v2.0 production flip

| Artifact | Path | Purpose |
|----------|------|---------|
| Counsel signoff PDF | `docs/legal/maa_v2_signoff.pdf` | Explicit approval of `MAA_TEXT_V2_0` at a named commit SHA |

See `docs/MAA_V2_PROMOTION_CHECKLIST.md` and `docs/MAA_V2_FLIP_RUNBOOK.md`.

After the PDF is committed:

1. Set `RMC_MAA_V2_PROMOTION_APPROVAL_TOKEN` in the deployment environment.
2. Remove the `[DRAFT v2.0 — PENDING COUNSEL REVIEW]` header from `_TEMPLATE_V2`.
3. Run `python scripts/preflight_maa_v2_flip.py` (must exit 0).
4. Run `RMC_MAA_V2_PROMOTION_APPROVAL_TOKEN=… python manage.py promote_maa_v2 --apply`
   **or** use `/super/migration/maa/v2-counsel-activate/`.
5. Set `RMC_MAA_DEFAULT_VERSION=v2.0` in production and deploy.

## Required before FACTS / Skyward SIS write-back

| Artifact | Path | Purpose |
|----------|------|---------|
| Counsel letter | `docs/legal_correspondence/<date>_facts_skyward_writepath_signoff.pdf` | Answers CFAA / DMCA §1201 / state trespass questions |

See `docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md` and
`docs/FACTS_SKYWARD_WRITE_PATH_FLIP_RUNBOOK.md`.

Until those PDFs exist, companion write surfaces remain `// honest-stub:` and
`assert_vendor_write_authorized()` refuses every write.
