# MAA v2.0 Promotion Checklist

**Owner:** Founder / on-call legal counsel.
**Status:** PLUMBING SHIPPED v3.34.0 (2026-05-18). **PROMOTION IS NOT YET PERFORMED.**
**Last updated:** v3.34.0, 2026-05-18.

This document is the operator runbook for promoting the
**Migration Authorization Agreement (MAA) v2.0** body from
counsel-pending DRAFT to platform default. The plumbing was shipped
in v3.34.0 so that the actual promotion is a **one-config-flip + one
small code edit**; this document covers the pre-conditions to verify
first, the procedure itself, and the rollback path.

---

## 0. What the platform currently does (today, pre-flip)

* `apps/migration_cloud/services/maa_text.py` registers
  `AGREEMENT_VERSIONS = {"v1.0": ..., "v2.0": ...}` with
  `AGREEMENT_VERSION_CURRENT = "v1.0"` and
  `MAA_TEXT_DRAFT_VERSIONS = {"v2.0"}`.
* `apps/migration_cloud/companion_receiver.py::MASignView` refuses any
  POST that requests `agreement_version=v2.0` (returns
  `400 code=draft_version`).
* `apps/migration_cloud/companion_receiver.py::MASignView` ALSO
  refuses any POST that supplies a `submitted_signature_text` whose
  SHA-256 matches a draft version body (returns
  `400 code=draft_signature_attempt`).
* Tenants in `settings.MIGRATION_CLOUD_MAA_OPTIN_TENANT_IDS` (set via
  the `RMC_MAA_V2_OPTIN_TENANT_IDS` env var) get a PREVIEW of v2.0
  text on the `maa_text` endpoint, rendered with
  `is_preview=True, preview_banner="PREVIEW — not yet active"`. The
  signature_text actually captured at POST time is STILL v1.0 — the
  preview is read-only.
* The env var `RMC_MAA_DEFAULT_VERSION` defaults to `v1.0`.

**Net result:** no operator can bind v2.0 today, regardless of
opt-in status. v2.0 exists only as preview text and unit-test
fixtures.

---

## 1. Pre-conditions before promoting v2.0 to default

All six items below MUST be completed before flipping the env var. The
order matters; later items depend on earlier ones.

### 1.1. External counsel written sign-off filed

* File path: `docs/legal/maa_v2_signoff.pdf` (this is a placeholder
  — the actual PDF MUST be added to the repo before the flip).
* Required content of the signoff memo:
    * Date the memo was issued
    * Attorney name + bar admission jurisdiction + license number
    * Explicit statement that the verbatim text of `MAA_TEXT_V2_0`
      (as of the commit SHA recorded in the memo) is approved for
      production use
    * Any sub-jurisdictional caveats (e.g. "OK in US, requires
      additional language for EU/UK")
* If the PDF is absent, **do not** proceed.

### 1.2. All 5 verbatim phrases preserved in `MAA_TEXT_V2_0`

The v2.0 body must continue to contain (case-insensitive, exact
substring):

1. `"scope of access"`
2. `"data minimization"`
3. `"no retention beyond migration"`
4. `"right to withdraw at any time"`
5. `"data subject rights"`

These are the counsel-blessed verbatim phrases that were the basis
for the signoff in 1.1 and are guarded by
`test_v2_verbatim_phrases_present` in
`apps/migration_cloud/tests/test_maa_v2_and_compliance_v3_33.py`. If
any phrase is missing the test trips and the wave halts.

### 1.3. v1.0 signatures remain backwards-compatible

* Existing signed `MigrationAuthorizationAgreement` rows that
  carry `agreement_version="v1.0"` MUST remain queryable + valid
  after the flip — they retain their snapshot of the v1.0 body in
  the `signature_text` column.
* Test guard:
  `test_hypothetical_flip_v1_historic_signatures_still_queryable` in
  `apps/migration_cloud/tests/test_maa_v2_promotion_plumbing_v3_34.py`.

### 1.4. Re-sign campaign plan documented

The flip does NOT auto-roll existing operators to v2.0. They retain
their v1.0 signatures, which remain valid for already-accepted
uploads. To collect v2.0 signatures going forward, plan a re-sign
email campaign:

1. Draft the operator-facing email (subject:
   "Action required: review updated Migration Authorization
   Agreement").
2. Include the human-readable diff between v1.0 and v2.0 (the four
   added clauses: Scope of Access, Data Minimization, Data Subject
   Rights, Right to Withdraw at Any Time).
3. Link to the re-sign URL in the operator portal.
4. Set a 30-day window for operators to re-sign before automated
   nudges escalate to phone/SMS reminders.

### 1.5. DSAR runbook re-reviewed for v2.0 clause references

* `docs/DSAR_RUNBOOK.md` references the data-subject-rights clauses
  in v2.0 (`right to access`, `right to erasure`, etc.). After flip,
  this becomes the binding text rather than a forward-looking
  reference. Audit the runbook for any "v2.0 will say..." phrasing
  and convert to present tense.

### 1.6. DPA template re-cross-linked

* `docs/DPA_TEMPLATE.md` cites `MAA § 10` (Data Subject Rights) for
  the data-subject-rights routing language. After flip, verify the
  section number still aligns (v2.0's Data Subject Rights section is
  numbered 10; this is stable but the audit closes the loop).

---

## 2. Flip procedure (counsel-signoff lands → production)

When all six pre-conditions in § 1 are confirmed:

### 2.1. Add the counsel signoff PDF to the repo

```bash
git add docs/legal/maa_v2_signoff.pdf
git commit -m "Add counsel signoff PDF for MAA v2.0 promotion"
```

The PDF is small (typically <1 MB); commit it directly. The repo
already accepts PDF binaries under `docs/legal/` (gitignore does
not exclude this path).

### 2.2. Edit `maa_text.py`: remove "v2.0" from the draft set

In `apps/migration_cloud/services/maa_text.py`, change:

```python
MAA_TEXT_DRAFT_VERSIONS: set[str] = {"v2.0"}
```

to:

```python
MAA_TEXT_DRAFT_VERSIONS: set[str] = set()
```

ALSO update `AGREEMENT_VERSION_CURRENT`:

```python
AGREEMENT_VERSION_CURRENT = "v2.0"
```

Then update the module docstring's "v3.33.0 adds the **v2.0 DRAFT**
body..." paragraph to reflect the promotion (mark the prior text as
historic and add the new active-version paragraph).

Commit:

```bash
git commit -am "Promote MAA v2.0 from draft to default (counsel signed off YYYY-MM-DD)"
```

### 2.3. Set the env var in production

In the production runtime (Render / k8s / your hosting layer):

```
RMC_MAA_DEFAULT_VERSION=v2.0
```

Deploy. The change goes live on the next dyno cycle. No migration is
needed — the version flip is a settings concern only.

### 2.4. Email operators with the re-sign link

Send the campaign drafted in § 1.4 to all operators with active
MAAs. Tracking: monitor the
`MigrationAuthorizationAgreement.objects.filter(agreement_version="v2.0").count()`
metric vs the operator population.

### 2.5. Monitor re-sign rate for 30 days

* Target: 80%+ re-sign within 30 days.
* If re-sign rate stalls below 50% at day 14, send a second email
  with a personalised subject line.
* Operators who never re-sign keep their v1.0 signatures. They are
  NOT blocked from uploading; v1.0 remains a registered (non-draft)
  version in `AGREEMENT_VERSIONS`.

---

## 3. Rollback procedure (if counsel raises post-flip concerns)

In the event counsel withdraws or restricts their signoff after the
flip:

### 3.1. Revert the env var

In production:

```
RMC_MAA_DEFAULT_VERSION=v1.0
```

Deploy. New signs go back to v1.0 immediately.

### 3.2. Re-add "v2.0" to the draft set

In `apps/migration_cloud/services/maa_text.py`:

```python
MAA_TEXT_DRAFT_VERSIONS: set[str] = {"v2.0"}
```

Also re-set `AGREEMENT_VERSION_CURRENT = "v1.0"`. Commit + deploy.

This will START refusing NEW v2.0 signs (the `draft_version` 400)
but historic v2.0 signs remain captured. **NEVER delete historic
v2.0 signature rows** — they are tamper-evident audit records and
deleting them would destroy evidence of operator consent.

### 3.3. Notify affected operators

If a clause in v2.0 was specifically problematic, email operators
who already re-signed v2.0 to explain the situation and offer a
fresh v1.0 re-sign as a courtesy (their v1.0 signature was never
deleted, so this is paperwork only).

---

## 4. Test coverage

The promotion plumbing is covered by
`apps/migration_cloud/tests/test_maa_v2_promotion_plumbing_v3_34.py`:

* Default tenant: GET returns v1.0 active, no preview.
* Opt-in tenant: GET returns v1.0 active + v2.0 preview with
  `is_preview=True` + `preview_banner="PREVIEW — not yet active"`.
* Opt-in tenant: POST with v2.0 signature_text body
  → 400 `code=draft_signature_attempt`.
* Opt-in tenant: POST with v1.0 signature_text body → 200, captures
  v1.0.
* Hypothetical flip simulation (monkeypatch settings +
  `MAA_TEXT_DRAFT_VERSIONS`): POST with v2.0 signature_text
  succeeds; v1.0 historic still queryable.
* `assertLogs` proves `signature_text` content NEVER logged.

These tests pass today against the plumbing. They are the safety
net for the flip — re-run them before deploying the env var change.

---

## 5. Open deferrals (do not block the flip but worth tracking)

* **Per-tenant MAA jurisdiction profiles.** Today every tenant gets
  the same v2.0 body. Multi-jurisdiction operators (e.g. a charter
  network spanning US + EU) may eventually need per-jurisdiction
  bodies. The plumbing's tenant-id-keyed resolver
  (`resolve_active_version_for_tenant`) is ready for that —
  generalize to a tuple `(tenant_id, jurisdiction)` when needed.
* **Signature ceremony recordings.** Counsel may request a video /
  audio recording of the operator's reading + acknowledgement.
  No infrastructure for that today.
* **Right-to-withdraw automation.** v2.0 § 12 promises a 48-hour
  stop-processing window after withdrawal notice. The current
  workflow is operator-driven (revoke MAA → manual sweep of pending
  uploads); a future enhancement could automate this via a
  scheduled task watching `MigrationAuthorizationAgreement.revoked_at`.
