# MAA v2.0 Flip Runbook (Wave 9 Agent N, v3.58.x)

**One-page operator runbook.** When counsel signoff lands, this is the
sequence you run. Cross-link: [`docs/MAA_V2_PROMOTION_CHECKLIST.md`](MAA_V2_PROMOTION_CHECKLIST.md)
is the long-form companion that explains *why* each step exists; this
runbook is the *what to type*, in order.

Owner: founder / on-call legal-ops.
Status: SHOVEL-READY (Wave 9, 2026-05-22). The actual flip is
intentionally NOT performed — it waits on counsel signoff PDF arrival.

---

## 0. Pre-conditions checklist (verify ALL before touching anything)

The preflight script below mechanically checks every item in this list.
Run it first:

```
python scripts/preflight_maa_v2_flip.py
```

Exit 0 = clean to proceed. Exit 1+ = stop, the message tells you which
condition failed.

The conditions, in order:

1. **Counsel signoff PDF on file.** `docs/legal/maa_v2_signoff.pdf`
   must exist and be a non-zero-byte file. The PDF itself is
   intentionally NOT in the repo today — counsel produces it
   externally and emails it; the legal-ops operator commits it before
   running the flip. See checklist § 1.1.
2. **`MAA_TEXT_V2_0` body is in non-draft shape.** The constant in
   `apps/migration_cloud/services/maa_text.py::_TEMPLATE_V2` must not
   carry the `[DRAFT v2.0 — PENDING COUNSEL REVIEW]` header anymore.
   The preflight greps the literal substring; if found, it refuses.
3. **All 5 counsel-blessed verbatim phrases preserved.** Checked
   against the `REQUIRED_VERBATIM_PHRASES` list in the existing
   verifier (`scripts/verify_maa_v2_promotion_readiness.py`).
4. **Promotion dashboard shows green readiness.** Visit
   `/super/migration/maa-v2-promotion/` (staff-only). Every check in
   Panel 1 reads `[OK]`.
5. **No in-flight signature campaigns.** Check
   `MigrationCloudMAACampaignNotification` for rows with
   `status="queued"`. If any exist, drain the queue first — the flip
   would otherwise send emails referencing the wrong active version.
6. **No environment-variable override accidentally still pointing
   to v1.0.** Confirm `RMC_MAA_DEFAULT_VERSION` is NOT set to
   `v1.0` in production secret store. (Default falls back correctly
   to v1.0 until you set it; the flip sets it to `v2.0`.)

---

## 1. Flip procedure (counsel signoff PDF in hand)

### 1.1. Commit the signoff PDF

```
git add docs/legal/maa_v2_signoff.pdf
git commit -m "Add counsel signoff PDF for MAA v2.0 promotion"
```

### 1.2. Run the preflight one more time

```
python scripts/preflight_maa_v2_flip.py --json
```

Must exit 0. If not, abort.

### 1.3. Run the management command (one operation, audit-trailed)

```
RMC_MAA_V2_PROMOTION_APPROVAL_TOKEN=<approval-token> \
    python manage.py promote_maa_v2 --apply
```

Without `--apply` the command dry-runs. The approval token must match
`settings.MAA_V2_PROMOTION_APPROVAL_TOKEN` via `hmac.compare_digest` —
this prevents an accidental flip by any operator who happens to have
shell access.

On success the command:

* edits `apps/migration_cloud/services/maa_text.py` (removes `"v2.0"`
  from `MAA_TEXT_DRAFT_VERSIONS` and bumps
  `AGREEMENT_VERSION_CURRENT` to `"v2.0"`);
* writes an append-only `MigrationCloudAuditEvent` of type
  `maa.v2_promotion_applied` (the meta-event is itself audited);
* re-runs the existing readiness verifier to confirm green-state
  post-flip;
* prints the diff applied + the audit-event UUID prefix.

### 1.4. Set the production env var

In Render / k8s / your hosting layer:

```
RMC_MAA_DEFAULT_VERSION=v2.0
```

Deploy. The change goes live on the next dyno cycle. No migration is
needed — the version flip is a settings concern only.

### 1.5. Run the post-flip verifier

```
python scripts/verify_maa_v2_promotion_readiness.py
```

Must exit 0. Saves a JSON report to `var/maa-v2-readiness-<utc>.json`
for the audit trail. This is the same verifier the promotion dashboard
runs in-process — running it from the CLI captures the
post-deployment state outside the dashboard's HTTP context.

### 1.6. Email operators with the re-sign link

See checklist § 1.4 + § 2.4 for the campaign details — the runbook
deliberately defers to the checklist for the human-facing comms.

---

## 2. Rollback procedure (if counsel raises post-flip concerns)

### 2.1. Revert the env var first (fastest mitigation — no code change)

```
RMC_MAA_DEFAULT_VERSION=v1.0
```

Deploy. New signs immediately revert to v1.0; historic v2.0 signatures
are preserved (NEVER delete them — they are tamper-evident audit
records).

### 2.2. Revert the code edit

```
git revert <commit-sha-of-promotion-edit>
```

This re-adds `"v2.0"` to `MAA_TEXT_DRAFT_VERSIONS` and re-sets
`AGREEMENT_VERSION_CURRENT = "v1.0"`. Commit + deploy.

### 2.3. Notify affected operators (see checklist § 3.3)

---

## 3. Post-flip verification

Run all four:

1. `python scripts/verify_maa_v2_promotion_readiness.py` (CLI; exit 0)
2. `python scripts/preflight_maa_v2_flip.py` (CLI; exit 0)
3. Visit `/super/migration/maa-v2-promotion/` — readiness green
4. Visit `/super/migration/audit/` — find the
   `maa.v2_promotion_applied` meta-event row

---

## 4. Files referenced by this runbook

* `apps/migration_cloud/services/maa_text.py` — `MAA_TEXT_V2_0`
  body + `MAA_TEXT_DRAFT_VERSIONS` set + `AGREEMENT_VERSION_CURRENT`.
* `apps/migration_cloud/management/commands/promote_maa_v2.py` —
  one-command flip with audit emission (Wave 9 Agent N).
* `apps/migration_cloud/companion_receiver.py` — `MASignView` enforces
  draft-version refusal at sign time.
* `scripts/preflight_maa_v2_flip.py` — stdlib preflight (Wave 9 Agent N).
* `scripts/verify_maa_v2_promotion_readiness.py` — existing 8-check
  verifier (v3.35.0 Agent 3).
* `docs/MAA_V2_PROMOTION_CHECKLIST.md` — deep companion document.
* `docs/legal/maa_v2_signoff.pdf` — counsel signoff (intentionally
  absent from repo until counsel produces it).

---

## 5. Why this exists as a separate document

The promotion checklist (`MAA_V2_PROMOTION_CHECKLIST.md`) is detailed
enough that operators new to the platform skim it nervously. This
runbook is the dense one-pager you keep open in a second tab while
running the flip. Both are SOT; if they ever drift, the
checklist is authoritative on the *why* and this runbook on the
*sequence of commands*.
