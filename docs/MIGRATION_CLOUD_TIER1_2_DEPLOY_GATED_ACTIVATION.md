# Migration Cloud — Tier 1 / 2 deploy-gated activation plan

**Status: 2026-08-08.** This is the operator runbook for the Migration Cloud
capabilities whose *code* is complete (or scoped) but whose *activation* is gated
on an infrastructure step, a Postgres-only deploy, or an external system. Nothing
here is faked or scaffolded: each item states exactly what already ships, the one
deploy gate that turns it on, how to verify it, and how to roll it back.

Legend:

- **CODE COMPLETE** — shipped, tested; activates on a config/infra deploy step.
- **PARTIAL** — a real, tested slice ships; the rest is an architecture change.
- **EXTERNAL** — cannot be honestly built without a live third-party system.

---

## 1. OCR always-on + confidence gate + needs-review lane — CODE COMPLETE

**What ships.** A scanned PDF whose text layer is empty auto-falls-through to OCR
(`apps/migration_cloud/pdf_extract.py::_try_ocr` / `_try_ocr_with_confidence` via
`pdf2image` + `pytesseract`). `extract_pdf_text_with_meta` reports whether OCR ran
plus its char count and mean per-word confidence; the PDF intake adapter
(`intake/pdf_intake.py`) feeds those to `tier3.ocr_confidence_warning`
(thresholds `migration_cloud.ocr.min_chars_for_decision` = 40 /
`low_confidence_threshold` = 0.5) and **routes a low-confidence result to the
needs-review lane** — refused with a precise reason instead of landing garbage
rows. Digitally-extracted PDFs skip the gate. Tests:
`tests/test_ocr_needs_review_gate_2026_08_08.py` (7).

**Deploy gate.**
1. Add the system binaries to the deploy image: **Tesseract OCR** + **Poppler**
   (`pdftoppm`). On Render's native runtime, `build.sh` vendors them under the
   repo-root `.ocr-env/` prefix (`.ocr-env/bin/tesseract`, `.ocr-env/bin/pdftoppm`,
   `.ocr-env/share/tessdata`); `pdf_extract._ocr_paths()` auto-discovers that
   prefix. Alternatively set `RMC_OCR_TESSERACT_CMD` / `RMC_OCR_POPPLER_PATH` /
   `TESSDATA_PREFIX` explicitly.
2. Add the Python libs to `requirements.txt`: `pytesseract`, `pdf2image`,
   `pdfplumber` (digital text; already common), `pypdf`.
3. Set env `RMC_OCR_ENABLED=1`.

**Verify.** Upload a digital-text PDF → lands normally. Upload a high-quality
scanned PDF → OCR runs, rows land. Upload a low-quality / near-blank scan → the
wizard shows the needs-review refusal ("… needs manual review before import").

**Rollback.** Unset `RMC_OCR_ENABLED` (or leave the binaries out). Scanned PDFs
degrade to the honest "install OCR" hint — exactly the pre-activation behaviour,
never a 500.

**Deferred (not blocking activation):** wire the same confidence gate into the
*connectionless* `FILE_UPLOAD` profiler path (`extract_pdf_tsv`), which currently
lands OCR output without the review gate. Tracked as a follow-up; the explicit
`IntakeMethod.PDF` path (the transcript-stack case OCR is built for) is gated.

---

## 2. Anti-virus / malware scanning on intake — CODE COMPLETE

**What ships.** Every Migration Cloud upload already routes through
`apps/security/upload_validation.py::validate_uploaded_file` (size + magic-byte
sniff) and `scan_for_malware()`; the MC intake pipeline calls it explicitly
(`services/intake_pipeline.py::_validate_export_upload` →
`scan_for_malware(_read_all(uploaded_file))`), and `_warn_malware_scanner_unconfigured`
logs when no scanner is wired. The scanner is pluggable via
`settings.UPLOAD_MALWARE_SCANNER` (a callable or dotted path). When unset it
returns `(True, "av-not-configured")` and logs — uploads stay size/type-gated,
never silently "clean".

**Deploy gate.**
1. Run a ClamAV daemon (`clamd`) reachable from the app (sidecar container, or a
   managed AV endpoint).
2. Point `UPLOAD_MALWARE_SCANNER` at a callable `f(data: bytes) -> (bool, str)`
   that streams the bytes to `clamd` (e.g. via `python-clamd`'s `instream`) and
   returns `(is_clean, signature_or_reason)`.

**Verify.** Upload the EICAR test string as a file → rejected with the signature
reason. Upload a clean CSV → passes.

**Rollback.** Unset `UPLOAD_MALWARE_SCANNER` → falls back to size/type gating with
the logged "unconfigured" warning.

---

## 3. Sandboxed parsing — PARTIAL

**What ships.** Parsing is size-capped, magic-byte-sniffed, AV-hooked (§2), and
per-row savepoint-isolated so a single bad row rolls back only itself. Spreadsheet
/ archive parsing runs in-process.

**The gap (architecture, spec-only).** True *sandboxing* = running the untrusted
parse in an isolation boundary so a malicious file that exploits a parser (zip
bomb, XML entity expansion, a native-lib CVE in `openpyxl`/`xlrd`/`pdf2image`)
cannot touch the app process or its secrets.

**Recommended design.**
- Move the parse step into a **separate worker process** with hard resource
  limits (CPU/mem/wall-clock via `resource.setrlimit` on POSIX or a cgroup), no
  network, and a read-only view of only the artifact bytes. Return only the
  canonical rows over a pipe.
- Or run it in a **short-lived locked-down container** (gVisor / nsjail /
  `--cap-drop=ALL --network=none --read-only`), which the `companion-docker`
  sibling already models for the extraction side.
- Add explicit zip-bomb guards (decompressed-size ceiling, entry-count cap) and
  disable XML external entities in every XML/XLSX path.

**Prerequisites.** A worker/queue topology decision (the platform already runs
Celery) and a resource-limit policy. No new third-party dependency required for
the subprocess approach.

---

## 4. RLS default-deny for Migration Cloud tables — SPEC (Postgres-only, deploy-sensitive)

**Why spec, not code.** Row-Level-Security is a **Postgres** feature; the SQLite
test harness cannot exercise it, and this repo has repeatedly shipped RLS deploy
blockers (see memory: `finding_rls_0083_phantom_migration_dep_deploy_blocker`,
`finding_rls_force_sweep_and_harness_gap`). Building it blind is exactly the
mistake those findings warn against — it must be authored and validated against a
production-parity Postgres, not merged from a green SQLite run.

**Design.**
- For each tenant-scoped MC table, `ALTER TABLE … ENABLE ROW LEVEL SECURITY` **and
  `FORCE ROW LEVEL SECURITY`** (unforced RLS is bypassed by the table owner — the
  75-table leak from the force-sweep finding), then add a **default-deny** policy
  plus an allow policy keyed on the request's tenant (`current_setting`).
- Superusers bypass RLS even with FORCE — keep the app's DB role non-superuser and
  wrap any legitimate cross-tenant maintenance in an explicit, ref-counted
  `rls_bypass` context (wrap the BODY, per the force-sweep finding).
- **Never add a dependency edge into an already-shipped migration** (NodeNotFound
  / InconsistentHistory) — new RLS policies go in a fresh leaf migration whose
  `RunSQL` is idempotent and reversible.

**Validation (mandatory before merge).** Run `migrate_schemas --shared` on a fresh
production-parity Postgres with `USE_DJANGO_TENANTS=1`; prove a cross-tenant SELECT
returns zero rows for a foreign tenant and the owning tenant still reads its own.

**Rollback.** The migration's reverse drops the policies + `NO FORCE`; keep it
tested so a bad rollout is one `migrate` back.

---

## 5. Eight partial vendor extractors — EXTERNAL (live SIS DOM)

**What ships.** The canonical-CSV ingest path is complete for all vendors (the
operator exports from the SIS's own UI and drops the file). Per-vendor *live*
extraction lives in `companion-extension/` (the operator's own authenticated
browser tab is the security boundary) with real extraction for PowerSchool /
Blackbaud / Veracross / Alma and **honest stubs** for FACTS / Skyward.

**What each needs.** A live authenticated session against that vendor to map its
current DOM / API shapes (they drift), plus a per-vendor contract test against
captured fixtures. This cannot be authored without access to the live system.

**Hard block.** FACTS + Skyward **write** paths stay `// honest-stub:` pending the
external-counsel docket (`docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md`) —
CFAA / DMCA §1201 / state computer-trespass. No feature flag may bypass this.

---

## 6. Real delta-sync source feed — EXTERNAL

**What ships.** The bundle already carries `diff_mode` / `diff_since` and the
apply path is idempotent (upsert-by-external-id), so re-applying a full export is
already non-duplicating. What's missing is a *source* that emits only the delta.

**What it needs.** A connector to a source system that supports change data
capture — a vendor webhook, a `updated_since` API, or DB CDC. Design: a connector
that pulls `changed_since=<last_cursor>`, lands the delta bundle, and advances the
stored cursor. Requires a live source that exposes deltas (external).

---

## 7. Certify one live vendor connector end-to-end — EXTERNAL

**What it needs.** A live vendor sandbox account and a certification matrix
(auth → discovery → mapping → dry-run → apply → reconcile → rollback) run against
real data, with the results recorded. Blocked on obtaining the sandbox account;
the connector framework (`models_connectors.py`, the connector admin gate) is
already in place to certify against.

---

## Summary

| Tier item | State | Gate to activate |
|---|---|---|
| 1 OCR always-on + review lane | **CODE COMPLETE** | Tesseract/Poppler in image + `RMC_OCR_ENABLED=1` |
| 2 AV / malware scan | **CODE COMPLETE** | `clamd` + `UPLOAD_MALWARE_SCANNER` |
| 3 Sandboxed parsing | PARTIAL | subprocess/container isolation (design in §3) |
| 4 RLS default-deny (MC) | SPEC | Postgres-validated FORCE-RLS migration (§4) |
| 5 Vendor extractors | EXTERNAL | live SIS session per vendor; FACTS/Skyward counsel-blocked |
| 6 Delta-sync feed | EXTERNAL | a source that emits deltas |
| 7 Live vendor cert | EXTERNAL | a vendor sandbox account |

Items 1–2 are one deploy step from live. Item 3 is a bounded internal
architecture change. Items 4–7 are gated on Postgres validation or external
systems and must not be scaffolded to look done.
