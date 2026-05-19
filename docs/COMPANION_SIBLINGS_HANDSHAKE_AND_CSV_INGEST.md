# Companion Siblings — RMC Platform Handshake and Canonical-CSV Ingest

**Shipped:** v3.37.0 Agent 4 (2026-05-19).
**Scope:** `companion-tauri/` (desktop appliance) and `companion-docker/`
(server appliance). Both siblings keep identical operator UX where
possible — same four-step wizard, same canonical-domain map, same
sealed-box semantics.

## 1. Architectural boundary (READ FIRST)

The Migration Cloud pivot ships THREE companion form-factors:

| Companion | Purpose | Programmatic SIS auth? |
|---|---|---|
| `companion-extension/` | Browser MV3 extension. Vendor data extraction runs in the operator's OWN authenticated SIS tab. | YES — operator's tab, operator's session, operator's consent. |
| `companion-tauri/` | Desktop appliance (Rust + Tauri 2.x). RMC platform handshake + canonical-CSV ingest only. | **NO**. |
| `companion-docker/` | Server appliance (FastAPI + httpx). RMC platform handshake + canonical-CSV ingest only. | **NO**. |

Vendor data extraction (PowerSchool / Blackbaud / Veracross / Alma /
FACTS / Skyward) lives in `companion-extension/` only. The operator's
own authenticated browser tab is the security boundary. The Tauri
and Docker siblings serve **two** purposes only:

1. **RMC platform handshake** — log into RunMyCampus itself (our own
   platform, already-authorized API), fetch the MAA text, prompt the
   operator to sign, sealed-box-upload the signed blob, retrieve the
   receipt.
2. **Canonical-CSV file ingest** — the operator manually exports CSV
   from their SIS via the SIS's own export UI (their browser, their
   session, their consent), then drops the CSV file into the Tauri
   or Docker appliance, which canonicalizes it against
   `DOMAIN_CANONICAL_HEADERS` and sealed-box-uploads.

If you find yourself adding `reqwest::get("https://<sis>...")` to
`companion-tauri/` or `httpx.get("https://<sis>...")` to
`companion-docker/`, **stop**: that work belongs in
`companion-extension/` instead.

## 2. Four-step operator flow (identical in both siblings)

### Step 1 — RMC platform login

Endpoint: `POST /api/v1/auth/login/` on the RunMyCampus server.
Bearer token returned by the server is held in memory only — never
persisted to disk, never logged.

- Tauri sibling: `rmc_handshake::login(server_url, Credentials)` →
  `SessionToken`. `Credentials` and `SessionToken` both impl
  `zeroize::ZeroizeOnDrop`.
- Docker sibling: `RMCSession.login(email, password)` →
  bearer string. The endpoint at `POST /handshake/login` returns the
  token to the caller; the in-memory copy is cleared immediately via
  `RMCSession.clear_token()`.

### Step 2 — MAA fetch + sign

Mirrors the existing `apps/migration_cloud/companion_receiver.py`
contract:

- `GET /api/v1/migration/maa/text/?vendor=<v>&tenant=<slug>` →
  verbatim MAA body, `active_version`, `is_draft` flag.
- `POST /api/v1/migration/maa/sign/` with `submitted_signature_text`
  echoed back so the server constant-time-compares against its own
  rendered active-version body. If the operator submitted a DRAFT
  body, the server refuses with `draft_signature_attempt`.

### Step 3 — Canonical-CSV pick & preview

The operator opens their SIS in their own browser tab, signs in
themselves, uses the SIS's own export UI to save a CSV to disk, then
picks the file in the appliance.

The appliance parses the CSV (header row + records), then runs
`match_canonical_domain(headers)`. The match function returns the
canonical-domain name with the highest header overlap above
`HEADER_MATCH_MIN_HITS = 3` (mirrors the Django accelerator).
Domains: students, staff, guardians, enrollment, sections, attendance,
grades, behavior, finance, transcripts, health, payroll,
communications, events, library, transport, transport_assignments,
hostel, hostel_assignments, cafeteria, cafeteria_assignments, alumni,
compliance — 23 canonical domains total.

### Step 4 — Sealed-box upload

Plaintext is the canonical-serialized JSON of the rows (sorted by
external-id-like column, keys sorted). Sealed-box encryption is
libsodium `crypto_box_seal` over the recipient's X25519 public key
(mirrors `companion-extension/src/lib/crypto.ts`). The ciphertext is
POSTed multipart to `/api/v1/migration/companion/upload/` with
metadata JSON carrying `maa_id`, `client_idempotency_key`,
`ciphertext_sha256`, `domain`, and `source`.

The server returns a `receipt_id` + `bundle_id`. The
`canonical_sha256` of the plaintext (NOT the ciphertext) is returned
to the operator so two uploads of the same input prove identical
canonical bytes even though sealed-box ciphertexts differ each time
(random nonce per call).

## 3. Per-vendor manual export (paragraph each)

Each paragraph links the operator to the vendor's own export UI. The
appliance NEVER drives this step.

- **PowerSchool**: Operator signs into PowerSchool Admin (`/admin/`),
  opens *Data Export Manager*, selects the canonical fields (we ship
  a header crosswalk in `companion-extension/`), exports to CSV. Drop
  the file into the appliance. PowerSchool documents this flow at
  `https://docs.powerschool.com/PSH/data-export-manager`.
- **Blackbaud**: From the Education Management module, open *Lists* →
  *Manage Lists*, build a list with the canonical columns, export as
  CSV. Drop into the appliance. Blackbaud's own help center has the
  list-export walkthrough.
- **Veracross**: Open the relevant *Axiom* query, run, then *Export to
  CSV*. Drop into the appliance. Veracross documents query export in
  their *Axiom Query Builder Manual*.
- **Alma**: From the *Reports* tab, build a report on the canonical
  fields, export CSV. Drop into the appliance. Alma's help center
  covers report builder + CSV export.
- **FACTS**: **No programmatic auth.** Operator signs into FACTS
  Family Portal / SIS via their own browser, uses the SIS's
  native export action (typically *Reports* → *Custom Reports* →
  *Export CSV*). Drop into the appliance.
- **Skyward**: **No programmatic auth.** Operator signs into Skyward
  via their own browser (ASPX session + CSRF tokens make programmatic
  scraping unsafe and unauthorized). Use Skyward's *Data Mining*
  module to build the export, save CSV, drop into appliance.

## 4. Canonical-header alignment rules

The canonical headers map ships as a JSON file alongside the modules:

- Tauri: `companion-tauri/src-tauri/src/canonical_headers.json`
  (embedded into the binary via `include_str!`).
- Docker: `companion-docker/app/canonical_headers.json` (loaded at
  module-import time via `load_canonical_headers`).

Both files mirror
`apps/migration_cloud/accelerators/runmycampus_canonical.py::DOMAIN_CANONICAL_HEADERS`
exactly. When that map changes server-side, both JSON files MUST be
updated in the same commit; a follow-up CI gate could lock this with
a hash check.

Matching is header-only — cell values pass through verbatim. Unknown
vendor columns are preserved under their original header name; the
server-side mapper routes them to `custom_fields` automatically.

## 5. Sealed-box guarantee

- Libsodium `crypto_box_seal` = X25519 ephemeral key + XSalsa20-Poly1305.
- Random nonce per call, so two uploads of the same plaintext produce
  different ciphertext bytes.
- Plaintext is canonical-serialized JSON; `canonical_sha256` (over the
  plaintext) is what we return to the operator for idempotency
  verification. The ciphertext SHA-256 is sent in the metadata so the
  server can verify integrity before persisting.
- The server-side decrypt hook
  (`apps/migration_cloud/companion_receiver.py::CompanionDecryptHookView`)
  uses the per-tenant `MigrationCloudCompanionKeypair` (v3.34.0). The
  pubkey is fetched at runtime via
  `GET /api/v1/migration/companion/server-pubkey/?tenant=<slug>`.

## 6. Receipt-id chain

Every successful upload returns:
- `receipt_id` (PK on `CompanionUploadReceipt`).
- `bundle_id` (FK to `MigrationBundle`).
- `canonical_sha256` (SHA-256 of the plaintext, returned by the
  appliance — NOT sent to the server).

The operator can then visit the RMC operator portal at
`/super/migration/<bundle_id>/` to advance through the existing
v3.28.0 wizard pipeline (preflight, mapping, reconciliation, apply).

Receipts are immutable. Re-uploads with the same
`client_idempotency_key` short-circuit on the server (return the
existing receipt without creating a second blob).

## 7. Secret hygiene contract (zero-tolerance)

NEVER log: passwords, bearer tokens, MAA signature_text bodies,
sealed-box ciphertext, sealed-box plaintext, canonical-csv cell
values.

ALWAYS log: HTTP status codes, bundle/receipt IDs, tenant slug,
canonical-domain name, row count, ciphertext SHA-256 prefix (first
12 hex chars).

### Tauri sibling secret hygiene

- `Credentials` and `SessionToken` impl `zeroize::Zeroize` +
  `ZeroizeOnDrop`. `Debug` output of either prints `<redacted>` for
  the secret fields.
- Token comparison uses `subtle::ConstantTimeEq`.
- The Tauri `invoke` handlers forward the bearer string as an
  argument; the frontend never persists it to localStorage.

### Docker sibling secret hygiene

- Python has no native zeroize, but `RMCSession.clear_token()`
  overwrites the in-memory token string with zeros and drops the
  reference. Endpoints clear the token at the end of each request.
- Constant-time string compare uses `hmac.compare_digest`.
- `bare except` is forbidden; every exception is typed.
- `subprocess(... shell=True)` is forbidden.
- `print()` is forbidden; all output goes through `logging`.

## 8. Vendor-specific pre-processor rules (v3.38.0)

Each vendor's stub body under `companion-tauri/src-tauri/src/extractors/`
and `companion-docker/app/extractors/` is replaced in v3.38.0 with a
REAL pre-processor — a pure function `preprocess_rows(rows) -> rows`
that normalizes vendor-specific quirks BEFORE the canonical-header
mapper runs. The pre-processor takes an already-parsed CSV (the
operator manually exported it via the SIS's own export UI) and never
touches the network.

Vendor detection lives in `extractors::detect_vendor(headers)` (both
languages) and scores headers by signature-overlap; the highest
scorer wins, ties broken alphabetically for determinism.

| Vendor      | Detection signature                                     | Pre-processor rules                                                                                                                                                                                                                                                                                       |
|-------------|---------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| PowerSchool | `student_number`, `dcid`, `enroll_status`, `lastfirst`  | `"Student Number"` → `external_id`. `"LastFirst"` → split on first comma into `last_name` + `first_name`. Date `MM/DD/YYYY` → `YYYY-MM-DD`. Gender `M`/`F`/`O`/`U` pass-through. Status `A`/`I`/`T`/`G` → `active`/`inactive`/`transferred`/`graduated`. Invalid dates pass through verbatim.               |
| Blackbaud   | `student_firstname`, `student_id`, `relationshiptype`   | Dot-nested headers flatten: `"Student.FirstName"` → `first_name`. Date `YYYY-MM-DDTHH:MM:SS[Z]` truncated to `YYYY-MM-DD`. Relationship rows (`RelationshipType` present) route `User.Id`/`Constituent.Id`/`Host.Id` → `guardian_external_id`. `RelationshipType` ∈ {Mother, Father, Guardian, …} lowercased into `guardian_relationship`. |
| Veracross   | `person_id`, `sex`, `household_id`, `studentemail`      | Role-partitioned columns: `Role` ∈ {Student, Faculty, Staff, Parent} picks the matching role-prefixed column (e.g. `StudentEmail` vs `FacultyEmail`). Date `M/D/YYYY` (single-digit) → `YYYY-MM-DD`. `"Sex"` → `gender`. `Person ID` → `external_id` (or `staff_external_id`/`guardian_external_id` by role). |
| Alma        | `alma_id`, `school_users_id`, `extra_attributes`         | JSON-in-cell parsed safely + flattened one level (e.g. `"{""grade"":""9""}"` → `grade=9`). Parse failure preserves raw cell. Literal `"null"` (case-insensitive) → empty string. `alma_id`/`school_users_id` → `external_id`. `user_type` → `role`. Output sorted by key for determinism.               |
| FACTS       | `familyid`, `personid`, `tuition_balance`                | ASPX export: separator + line-ending handling is the parser's job; pre-processor strips stray `\r` from cell values. Date `MM/DD/YY` → ISO with year-window 00-49 → 2000s, 50-99 → 1900s. `FAMILYID` → `household_id`. `PERSONID` → `external_id`. Write-path fields (`tuition_balance`, status) routed under `read_only_` prefix per v3.34 counsel docket (`# honest-stub: write-path counsel-blocked`). |
| Skyward     | `skyward_id`, `other_id`, `name_id`, `entity_id`         | Legacy-Mac `\r` line endings: cell-value trailing `\r` stripped defensively. ALL_CAPS_UNDERSCORE column names normalized to lowercase. Compact date `YYYYMMDD` (8 digits) → `YYYY-MM-DD`; already-ISO passes through. `SKYWARD_ID`/`OTHER_ID` → `external_id`. Write-path fields (`STATUS`, `BALANCE`) routed under `read_only_` prefix per v3.34 counsel docket. |

### Architectural boundary — re-asserted

No vendor pre-processor imports `reqwest::Client` (Rust) or
`httpx`/`requests`/`urllib3`/`aiohttp` (Python). The Python test
`test_no_network_imports_in_extractors` scans every module in
`companion-docker/app/extractors/` and asserts none of those tokens
appear. The Rust `extractors/` modules likewise have zero `use`
statements that touch network crates.

The pre-processors are **pure functions over already-parsed data**:
input is the CSV the operator manually exported from their SIS's own
export UI, output is normalized rows ready for the canonical-header
mapper. There is no programmatic SIS login, no cookie capture, no
session replay, no DOM scraping, no third-party HTTP call — those
remain exclusively in `companion-extension/` where the operator's own
authenticated browser tab is the security boundary.

### Test counts

- Rust: 36+ inline `#[test]` cases (6 per vendor) plus 6
  `detect_vendor` integration tests in `canonical_csv.rs` via
  `parse_and_preprocess`. Determinism is asserted for PowerSchool and
  Alma at minimum.
- Python: 56 pytest cases in
  `companion-docker/tests/test_extractors_v3_38.py`, including the
  architectural-boundary import-scan test. All 56 pass without
  external deps; existing v3.37.0 suite (14 pass + 5 PyNaCl/fastapi
  skips) preserved → 70 total in the companion-docker suite.

## 9. Deferred follow-ups (v3.39+)

- A CI gate that hash-locks `canonical_headers.json` against the
  Django source-of-truth `DOMAIN_CANONICAL_HEADERS`.
- A signed packaging pipeline for the Tauri appliance (Apple
  notarization + Windows code-signing).
- FACTS / Skyward write-path unblock pending counsel signoff in
  `docs/FACTS_SKYWARD_WRITE_PATH_COUNSEL_REVIEW.md` — until then,
  the `read_only_*` prefix routing is the durable interim contract.
