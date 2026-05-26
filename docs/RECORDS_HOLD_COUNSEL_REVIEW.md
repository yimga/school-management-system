# Records-hold + transcript-release counsel docket

**Status:** OPEN — counsel review pending
**Owner:** Compliance + Legal
**Last touched:** 2026-05-26 (Wave S-D, v3.96.1)

This docket frames the legal questions external counsel must answer before
specific records-hold categories can be enforced as hard-blocks on
transcript release.

## Hold categories (registry)

| Category | Default severity | Counsel-pending? | Notes |
|---|---|---|---|
| `financial` | hard | No | Industry-standard practice; most jurisdictions permit. |
| `academic` | hard | No | Required by accreditation in many jurisdictions. |
| `library` | soft | No | Routinely a soft warning, not a hard block. |
| `incomplete_paperwork` | soft | No | Soft warning; cleared by uploading missing docs. |
| `disciplinary` | soft | **Yes** | Several US states + UK consider disciplinary holds discriminatory if used to deny basic records access. |
| `counsel_review` | hard | **Yes** | Catch-all when a school's counsel needs to review before release. |

## Questions for counsel

1. **Disciplinary holds — discrimination risk.**
   In what jurisdictions is it legally permitted to block transcript release
   based on an unresolved disciplinary investigation (vs. a finalized
   disciplinary record)? Specifically:
   - US: § 504 / ADA / state ed-codes (e.g. NY § 2-d, IL P.A. 100-0825).
   - UK / EU: GDPR Art. 17 (right to erasure conflict if disciplinary
     records keep transcript blocked indefinitely).
   - Canada: PIPEDA / FIPPA equivalents.

2. **Financial holds — fair-debt / consumer-protection.**
   At what fee-balance threshold (relative to local minimum wage / cost
   of living) does blocking a transcript shift from "reasonable business
   practice" to "constructive denial of education"? Per-jurisdiction
   answer required for global rollout.

3. **Records-release SLA.**
   Statutory maximum response time on a written transcript-release request
   per FERPA (US) / GDPR Art. 15 (EU) / state-specific equivalents. The
   kernel currently has no SLA timer.

4. **Soft warnings vs. hard blocks — what disclosures are required?**
   When the kernel allows release but emits a `soft_warning`, what
   disclosure must accompany the transcript? (e.g., "Note: $250 outstanding
   library balance.")

5. **Re-enrollment vs. transcript release.**
   Some jurisdictions allow holds on _re-enrollment_ but require transcript
   release even when balance is owed. Confirm per-jurisdiction.

## Current default posture (pre-counsel)

Until counsel signoff PDFs are filed under `docs/legal/`:

- `disciplinary` defaults to **soft warning** (the kernel's default), NOT
  a hard block. Operators in jurisdictions where hard-block is established
  practice can override per-student with `severity_override="hard"`.
- `counsel_review` defaults to **hard block** but the verbatim reason MUST
  cite the counsel docket entry (the form refuses 5-char reasons).
- `financial` defaults to hard for now (industry-standard) but is on the
  counsel docket for jurisdiction-specific threshold rules in v3.97+.

## Implementation pointer

- Kernel: `apps/student360/records_hold_kernel.py`
- Tests: `apps/student360/tests/test_records_hold_kernel.py`
- Storage: `School.settings["records_holds"][student_id]` — ZERO new migrations
- Release decision: `can_release_transcript(student_id, holds)` returns
  `ReleaseDecision(can_release, hard_blockers, soft_warnings)`

## Closeout criteria

To close this docket, the following must land:

- `docs/legal/records_hold_counsel_signoff.pdf` (signed counsel opinion)
- Per-jurisdiction severity override map in
  `apps/student360/records_hold_jurisdiction_overrides.py` (currently absent)
- Statutory SLA timer in the kernel (currently absent)
- CI gate `scripts/verify_records_hold_counsel_signoff_present.py`
  (modeled on `verify_honest_stubs_intact.py`)

Until all four land, treat the kernel as a policy-framework scaffold —
production schools should keep `disciplinary` as soft and operate the
counsel-review category via per-tenant manual review.
