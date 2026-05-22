# FACTS / Skyward Write-Path Flip Runbook (Wave 9 Agent N, v3.58.x)

**One-page operator runbook.** When counsel unblocks the FACTS or
Skyward write paths, this is the sequence you run. Cross-link to the
deep companion: [`docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md`](FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md)
which is the open counsel docket and the authoritative source of *why*
the write paths are blocked today.

Owner: founder / on-call legal-ops.
Status: SHOVEL-READY (Wave 9, 2026-05-22). The actual unblock is
intentionally NOT performed — it waits on counsel written response to
the questions in the docket.

---

## 0. What the platform does today (pre-flip)

* `companion-extension/src/vendors/facts.ts` and
  `companion-extension/src/vendors/skyward.ts` contain literal
  `// honest-stub:` markers on every write surface. The Companion
  extension client-side will NOT POSTBACK to FACTS / Skyward. This is
  documented in the docket and is the legal-isolation surface.
* The Tauri + Docker siblings (`companion-tauri/`, `companion-docker/`)
  also avoid programmatic SIS login by architectural design — see
  the auto-memory note `feedback_companion_siblings_no_programmatic_sis_login.md`.
* **Server-side gate** at
  `apps/migration_cloud/services/vendor_write_gate.py` (Wave 9 Agent N)
  refuses to authorize a vendor write unless BOTH a per-vendor approval
  token AND a per-vendor counsel-signoff SHA are provisioned in the
  environment AND the approval token validates via constant-time
  compare against `sha256(f"{vendor_slug}:{counsel_sha}")`. Future
  server-side write-path code MUST call
  `assert_vendor_write_authorized(vendor_slug)` before any mutating
  operation; the gate is the choke point.
* **Operator dashboard** at `/super/migration/vendor-write-status/`
  (staff-only) shows per-vendor authorization status — no token bytes
  or PDF content are surfaced; only the booleans "approval token
  configured" / "counsel-signoff SHA configured" / "authorized today".

**Net result:** even if a future write-path code path were added by
accident, the gate refuses unless the operator has explicitly
provisioned BOTH halves of the double-token. The companion-side stubs
remain literal `// honest-stub:` regardless.

---

## 1. Pre-conditions before flipping a vendor's write path

All five items below MUST hold before flipping a vendor (separately
for FACTS and for Skyward — the gate is per-vendor).

### 1.1. Counsel written response on file

* Counsel must answer the questions in
  `docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md` § 2 in writing.
* The response must explicitly identify the vendor (FACTS or
  Skyward — answer per-vendor; the docket treats them separately
  because their legal postures differ).
* Counsel response document is committed under `docs/legal/` as a
  PDF or signed memo (e.g. `docs/legal/facts_write_path_signoff.pdf`).

### 1.2. Counsel-signoff PDF SHA-256 computed

Compute the SHA-256 of the signoff PDF externally:

```
shasum -a 256 docs/legal/facts_write_path_signoff.pdf
# or on Windows:
certutil -hashfile docs/legal/facts_write_path_signoff.pdf SHA256
```

Save the 64-hex digest. It must be **lowercase** hex.

### 1.3. Approval-token computed

Compute the approval token externally:

```
python -c "import hashlib;print(hashlib.sha256(b'facts:<sha-from-1.2>').hexdigest())"
```

The result is the *approval token* — a 64-hex string bound to BOTH the
vendor slug AND the specific PDF. Rotating the PDF breaks the binding
on purpose — the operator must recompute and re-approve.

### 1.4. Env-var provisioning checklist

In the production secret store (Render / k8s / etc.):

```
RMC_VENDOR_WRITE_COUNSEL_SIGNOFF_SHA_FACTS=<sha-from-1.2>
RMC_VENDOR_WRITE_APPROVAL_TOKEN_FACTS=<token-from-1.3>
```

(or substitute `SKYWARD` for the other vendor).

Both env vars must be set. Either alone refuses.

### 1.5. Dashboard verification

Visit `/super/migration/vendor-write-status/`. The row for the vendor
must show:

* approval token: **set**
* counsel signoff SHA: **set**
* SHA well-formed: **ok**
* authorized: **yes**
* refusal reason: **—**

If any field is wrong, fix it before proceeding.

---

## 2. Flip procedure (counsel signoff PDF in hand)

The platform-side flip is **provisioning the two env vars** — that is
the entirety of the "flip". After that, future server-side write-path
code paths MUST call `assert_vendor_write_authorized(<vendor_slug>)`;
the gate authorizes the call only when both env vars match.

### 2.1. Commit the signoff PDF

```
git add docs/legal/<vendor>_write_path_signoff.pdf
git commit -m "Add counsel signoff PDF for <vendor> write-path unblock"
```

### 2.2. Provision the two env vars in production

```
RMC_VENDOR_WRITE_COUNSEL_SIGNOFF_SHA_<VENDOR>=<64-hex>
RMC_VENDOR_WRITE_APPROVAL_TOKEN_<VENDOR>=<64-hex>
```

Deploy. The change goes live on the next dyno cycle.

### 2.3. Verify on the dashboard

Visit `/super/migration/vendor-write-status/`. The vendor row should
flip to "authorized: yes". If not, the most common cause is a typo —
the token is the SHA-256 of `f"{vendor_slug}:{counsel_sha}"` exactly;
no trailing newline, no whitespace.

### 2.4. (Future) build the actual write-path code

Today there is intentionally NO server-side code that calls
`assert_vendor_write_authorized` — the gate is shovel-ready
infrastructure, not an active code path. Any future PR that adds a
vendor-mutating server-side surface MUST include a call to this gate
as its first statement. The PR review checklist for that PR includes:

* call to `assert_vendor_write_authorized(slug)` is the first
  statement in the write function;
* test coverage proves the function raises
  `VendorWriteNotAuthorizedError` when either env var is absent;
* CHANGELOG + counsel docket cross-link updated;
* `MigrationCloudAuditEvent.record()` emitted on every successful
  write (the gate is the authorization; audit is the trail).

---

## 3. Rollback procedure (if counsel withdraws signoff)

### 3.1. Revoke the approval token (fastest mitigation)

In production:

```
RMC_VENDOR_WRITE_APPROVAL_TOKEN_<VENDOR>=  # cleared
```

Deploy. The gate immediately starts refusing — any in-flight write
will raise `VendorWriteNotAuthorizedError` and the call site MUST
treat that as a refusal (no retry loop).

### 3.2. Clear the counsel SHA env

```
RMC_VENDOR_WRITE_COUNSEL_SIGNOFF_SHA_<VENDOR>=  # cleared
```

Deploy. Belt-and-suspenders — even if a leaked approval token
re-appears, the SHA env clearance keeps the gate closed.

### 3.3. Remove the signoff PDF from `docs/legal/` only if instructed

The PDF is forensic evidence of what counsel said and when. **Do NOT
delete it unless counsel explicitly directs.** Add a follow-up memo
in `docs/legal/` noting the withdrawal date + reason.

### 3.4. Notify any operators / customers who already used the path

If any write-path executions landed via the now-revoked authorization,
notify affected customers per the DSAR / breach-notification protocols
in `docs/DSAR_RUNBOOK.md`.

---

## 4. Post-flip verification

1. Visit `/super/migration/vendor-write-status/` — vendor row shows
   "authorized: yes".
2. Visit `/super/migration/audit/` — confirm no unexpected
   write-related audit events.
3. (When server-side code path lands) run the future
   `test_vendor_write_gate.py` test module — must be 100% green
   per-vendor.

---

## 5. Files referenced by this runbook

* `apps/migration_cloud/services/vendor_write_gate.py` — gate
  module (Wave 9 Agent N).
* `apps/migration_cloud/api/views_vendor_write_status.py` — staff-only
  dashboard view (Wave 9 Agent N).
* `templates/migration_cloud/super/vendor_write_status.html` — template.
* `companion-extension/src/vendors/facts.ts` —
  literal `// honest-stub:` markers on write surfaces (DO NOT edit;
  see docket).
* `companion-extension/src/vendors/skyward.ts` — same.
* `docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md` — open counsel
  docket; the authoritative *why*.
* `docs/legal/<vendor>_write_path_signoff.pdf` — counsel signoff
  (intentionally absent from repo until counsel produces it).

---

## 6. Why a server-side gate exists when the companion-side is stubbed

Defence in depth. The companion-side honest-stubs are the primary
security boundary; nothing the user's browser does will POSTBACK to
FACTS / Skyward. But a future server-side code path (vendor REST
adapter, scheduled sync task, etc.) could in principle land
independently of the companion code path. The gate ensures that even
a well-intentioned engineer who adds such a path MUST first run the
operator dance described in § 1 — there is no env-var-free fallback.
