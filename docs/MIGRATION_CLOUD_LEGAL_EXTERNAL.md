# Migration Cloud — LEGAL-EXTERNAL hand-off (for counsel)

> **Scope of this file.** These items are the *legal* work product of the 2026-07-24 Migration Cloud
> audit. Per the engineering directive, the **codebase scaffolding** for each (the hook, gate, record,
> honest boundary, and default-off stub) is implemented in the repo; the **binding legal artifact** is
> **external** and must be produced/finalized by counsel. Engineering must NOT write, bless, or
> feature-flag past any item below. Nothing here unblocks a counsel-gated code path.

Cross-references: [`MIGRATION_CLOUD_AUDIT_2026_07_24.md`](MIGRATION_CLOUD_AUDIT_2026_07_24.md),
[`DPA_TEMPLATE.md`](DPA_TEMPLATE.md), [`DSAR_RUNBOOK.md`](DSAR_RUNBOOK.md),
[`FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md`](FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md),
[`MAA_V2_PROMOTION_CHECKLIST.md`](MAA_V2_PROMOTION_CHECKLIST.md), [`legal/README.md`](legal/README.md).

| # | Item | Why it's blocking | Code state (done by eng) | Counsel deliverable |
|---|---|---|---|---|
| L1 | **Finalize the v1.0 MAA body** — the MAA actually binding operators today (`services/maa_text.py` `_TEMPLATE_V1`) is self-labeled *"operator-acknowledged but NOT yet counsel-finalized."* | Operators bind to unreviewed contract text on every migration. **Top priority.** | Sign flow, active-version resolution, constant-time verify all real; a new operator-visible "counsel-review pending" caveat is surfaced in the sign UI. | Counsel review + finalize `_TEMPLATE_V1`; confirm enforceability of the authorization-to-migrate representation. |
| L2 | **MAA v2.0 signoff PDF** → `docs/legal/maa_v2_signoff.pdf` | `promote_maa_v2` is counsel-token-gated; v2.0 stays DRAFT until this exists. | Draft-never-signed gates real + must-FIRE; promotion plumbing wired, flip NOT performed. | Approve `MAA_TEXT_V2_0` at a named commit SHA; deliver signed PDF. |
| L3 | **Finalize the DPA** (`DPA_TEMPLATE.md`, DRAFT) | GDPR Art. 28 processor terms + NY Ed-Law §2-d + the sub-processor list the MAA promises. | Retention/purge cadence in code matches the draft (90-day artifact, 7-year audit). | Finalize processor terms + sub-processor schedule. |
| L4 | **Finalize the DSAR runbook** (`DSAR_RUNBOOK.md`, DRAFT) | 30-day statutory procedure, redaction standard, controller-vs-processor routing. | `dsar_runbook_record` command + counsel-token purge gate real; event type now registered (no more masquerade). | Finalize the fulfillment procedure + legal SLAs. |
| L5 | **FACTS / Skyward write-back counsel letter** → `docs/legal_correspondence/<date>_facts_skyward_writepath_signoff.pdf` | CFAA / DMCA §1201 / state computer-trespass / *Power Ventures* / *Sony Betamax* analysis before any vendor-write path is wired. | Write paths are literal honest stubs; `assert_vendor_write_authorized` is an unwired forward-compat guard (dual-token, SHA-bound). No flag workaround. | Legal analysis + signoff before the gate is ever wired to a real write. |
| L6 | **Guardian-consent text + enforcement policy** (`_consent_text_v1.html`) | The FERPA "school official" / COPPA "school-as-agent" theory the MAA asserts, and the exact decline/revoke enforcement rule. | Consent record + a NEW apply-time enforcement gate are implemented; the *policy* (what counts as sufficient consent, per jurisdiction) drives the gate's threshold config. | Review consent wording; confirm the legal theory; specify the jurisdiction-by-jurisdiction consent-sufficiency rule. |
| L7 | **Governing-law + retention-window sign-off** | Delaware governing-law clause (MAA §10/§13), 90-day artifact purge, 7-year audit retention vs the strictest in-scope jurisdiction. | Windows enforced in code (`MIGRATION_CLOUD_DATA_RETENTION.md`). | Confirm windows + governing law against strictest in-scope jurisdiction. |

**Handling rule for engineering:** if any future change would require editing a document above, or would
wire `assert_vendor_write_authorized` to a real write, or would flip `RMC_MAA_DEFAULT_VERSION` to `v2.0` —
STOP and route to counsel. A default-off feature flag is explicitly **not** an acceptable substitute for any
of L1–L7.
