# FACTS / Skyward write-path — counsel review docket

**Version:** v3.34.0 (2026-05-18)
**Status:** OPEN — pending external counsel sign-off
**Owner:** RunMyCampus Engineering + Legal liaison

> **NOTE — this is a docket entry, not legal advice.** All statements
> below describe engineering posture and frame the questions counsel
> needs to answer. Final determinations on legal exposure are the
> exclusive province of external counsel. Engineering MUST NOT proceed
> on its own interpretation of the items below.

---

## 1. Why FACTS + Skyward are write-blocked today

Both vendors are blocked from automated *write* paths in the Companion
extension. Their read paths are limited to **safe-DOM scraping of
server-rendered directory printouts** the authenticated user could
already view (e.g. `/family/directorystudents.aspx` for FACTS,
`seplog01.w` directory listings for Skyward). Writes — anything that
mutates the vendor's state via POSTBACK — are stub-only.

### 1.1 FACTS SIS

* FACTS Family / SIS uses classic **ASP.NET WebForms** with
  `__VIEWSTATE`, `__VIEWSTATEGENERATOR`, and `__EVENTVALIDATION`
  hidden fields plus a rotating CSRF token on every page render.
  Programmatic POSTBACK requires either (a) re-extracting these
  tokens from a fresh `GET` and immediately POSTing back, or (b)
  reusing tokens captured during the user's interactive session.
* Either pattern can be characterized as **session impersonation**.
  In the United States, *Power Ventures v. Facebook* (9th Cir. 2016)
  held that continued access to a service after the operator has
  taken specific technical countermeasures (in that case, IP blocks
  + cease-and-desist letters) may constitute "exceeding authorized
  access" under the Computer Fraud and Abuse Act (18 USC § 1030).
* RunMyCampus has received no FACTS C&D to date, but the legal
  pattern is asymmetric: a *future* C&D could retroactively make our
  in-place automation "unauthorized" without code changes on our end.

### 1.2 Skyward

* Skyward Family / Educator Access also uses ASP.NET WebForms
  (`seplog01.w` and the `wreports` subtree). Same `__VIEWSTATE` /
  CSRF / session-cookie pattern as FACTS.
* Skyward has historically been more aggressive than FACTS toward
  third-party integrations per public records (SEC filings, press
  releases) — partner-program-gated API access is the supported
  channel, and unsupported automation has drawn cease-and-desist
  responses in the past.
* This shifts the *Power Ventures* analysis materially: Skyward's
  posture suggests they would issue a C&D earlier and more
  forcefully than FACTS.

---

## 2. Counsel review questions

These are the questions external counsel MUST answer (in writing,
filed in this docket below) before any write-path work begins.
Engineering does not have the standing to answer them.

### 2.1 CFAA scope under user delegation

> Does an authenticated parent or staff user **explicitly delegating
> their already-authorized browser session** to a local-device-only
> browser extension constitute *that user's own access* under the
> CFAA, or does it constitute *third-party access* by RunMyCampus?

* Sub-question (a): Does it matter that the extension runs locally
  on the user's own device, never sends the session to a RunMyCampus
  server, and is initiated by an explicit per-session click?
* Sub-question (b): Does the per-tenant MAA
  (Migration Authorization Agreement) — signed by an authenticated
  staff user with admin-tier delegation authority on the source
  system — change the analysis?

### 2.2 MAA + vendor TOS interaction

> If the vendor's Terms of Service forbid automation, does an
> MAA-signed authorization from an authenticated tenant administrator
> nonetheless survive CFAA scrutiny, by analogy to *Sony Corp. v.
> Universal City Studios* (1984) (Betamax — fair use of purchased
> access)?

* This is the closest US Supreme Court analog for "you bought it,
  you can automate your own use of it". The Betamax doctrine has
  been read narrowly in subsequent CFAA case law; we do not assume
  it covers us.

### 2.3 DMCA § 1201 exposure

> Reading rotating CSRF tokens (`__VIEWSTATE`, `__EVENTVALIDATION`)
> from the page DOM and re-submitting them with a subsequent POST —
> does this "circumvent a technological measure that effectively
> controls access" under DMCA § 1201 (17 USC § 1201)?

* Engineering's working assumption: **no**, because the user's own
  browser already has the tokens; we are not breaking encryption,
  guessing tokens, or bypassing authentication. We are simply
  re-submitting what the user's session already holds.
* But: this is exactly the kind of question that needs counsel
  sign-off. Get it in writing.

### 2.4 State-level computer-trespass law

> Each US state has its own variant of CFAA (e.g. California Penal
> Code § 502, New York Penal Law § 156). What is the worst-case
> state for FACTS' and Skyward's incorporation domicile?

* FACTS Management LLC: incorporated in Delaware; primary operations
  in Nebraska. **Sub-question:** does Nebraska Revised Statute
  § 28-1343 (Computer Crimes) have a broader "unauthorized access"
  definition than federal CFAA?
* Skyward, Inc.: incorporated in Wisconsin; HQ in Stevens Point, WI.
  **Sub-question:** does Wisconsin Statute § 943.70 (Computer
  Crimes) have a broader definition?

### 2.5 Non-US jurisdictions

> For tenants outside the United States, what is the analogous
> exposure under GDPR (Art. 32 — integrity & confidentiality), the
> UK Computer Misuse Act 1990, and Canada's Criminal Code § 342.1
> (unauthorized use of a computer)?

* Defer this until counsel has answered the US questions. The EU
  analysis turns on the data-controller / data-processor split,
  which is the subject of `docs/DPA_TEMPLATE.md`.

---

## 3. Mitigation pre-conditions

Before write paths are unblocked **all** of the following MUST be
true, and the corresponding evidence filed in this docket:

| # | Pre-condition | Evidence required |
|---|---|---|
| 1 | External counsel written sign-off addressing every question in §2 | Letter or memo from reviewing attorney, dated, on firm letterhead, filed in `docs/legal_correspondence/<date>_facts_skyward_writepath_signoff.pdf` |
| 2 | Per-vendor TOS review by counsel — current as of unblock date | Signed attestation that the current TOS does not foreclose the planned write pattern |
| 3 | Operator-side dual-confirm UX | Companion popup shows a verbatim TOS excerpt + requires the operator to check "I confirm I am authorized to perform this action on my own account" before each write session |
| 4 | Rate-limit hard cap | Companion code enforces ≤1 write per second per vendor session — non-bypassable. This is the "we are not a bot" defense if litigation ever materializes. |
| 5 | Audit-log immutable record | Every write captured with `who / what / when / vendor / row external_id` in `MigrationCloudWriteAudit` (or equivalent), retained ≥ 7 years, append-only |
| 6 | Tenant-side opt-in | Tenant administrator must enable a per-tenant `MigrationCloudWriteEnabled` flag before any write fires — defaults OFF; NEVER on at tenant creation |

**Engineering MUST NOT** add a feature flag to enable this with
`default-off`. The code stubs MUST remain literal `// honest-stub:`
until the sign-off is filed. A flag (even default-off) communicates
"this is a switch we can flip" — which is exactly the wrong frame.

---

## 4. Read-path safe-DOM contract (current state)

Per v3.33.0 and retained in v3.34.0:

### 4.1 FACTS

* Reads the authenticated user's directory listings via
  `/family/directorystudents.aspx` and equivalent staff directory
  endpoints — pages the user could already see in their browser.
* `companion-extension/src/vendors/facts.ts::extractFacts` parses
  the server-rendered HTML table into canonical rows.
* All write attempts (e.g. password reset, enrollment change,
  attendance mark) are guarded by `// honest-stub:` markers and
  emit `console.warn` to the operator: "this action was not
  performed; FACTS write paths are blocked pending counsel review".
* No `__VIEWSTATE` token is ever extracted, stored, or POSTed.

### 4.2 Skyward

* Reads the authenticated user's directory listings via
  `seplog01.w` directory printouts — same posture as FACTS.
* `companion-extension/src/vendors/skyward.ts::extractSkyward`
  parses the server-rendered HTML table.
* All write attempts are guarded by `// honest-stub:` markers + a
  console warning.

---

## 5. Honest deferral statement (v3.34.0)

> **Write paths to FACTS and Skyward remain BLOCKED in v3.34.0. They
> will not be unblocked until external counsel sign-off is filed in
> this docket (see §3). Engineering MUST NOT work around this
> blocker by introducing a feature flag (even default-off); the code
> stubs MUST remain literal `// honest-stub:` markers until the
> sign-off is filed. This deferral is documented as an honest
> limitation, not a TODO — it is a deliberate engineering posture
> derived from open counsel questions.**

---

## 6. Counsel sign-off log (to be filled by reviewing attorney)

| Date | Reviewing attorney | Question(s) addressed | Outcome | File path |
|---|---|---|---|---|
| _pending_ | _pending_ | §2.1 | _pending_ | _pending_ |
| _pending_ | _pending_ | §2.2 | _pending_ | _pending_ |
| _pending_ | _pending_ | §2.3 | _pending_ | _pending_ |
| _pending_ | _pending_ | §2.4 | _pending_ | _pending_ |
| _pending_ | _pending_ | §2.5 | _pending_ | _pending_ |

---

## 7. References

* **CFAA** — Computer Fraud and Abuse Act, 18 USC § 1030
* **DMCA § 1201** — Digital Millennium Copyright Act,
  anti-circumvention provisions, 17 USC § 1201
* ***Power Ventures, Inc. v. Facebook, Inc.***, 844 F.3d 1058
  (9th Cir. 2016) — continued access after technical countermeasures
  as exceeding authorized access
* ***Sony Corp. of America v. Universal City Studios, Inc.***,
  464 U.S. 417 (1984) — fair use of purchased / authorized access
  (Betamax doctrine)
* **California Penal Code § 502** — Comprehensive Computer Data
  Access and Fraud Act
* **Nebraska Revised Statute § 28-1343** — Unauthorized computer
  access (FACTS Management LLC domicile-relevant)
* **Wisconsin Statute § 943.70** — Computer crimes (Skyward, Inc.
  domicile-relevant)
* **NY Penal Law § 156** — Offenses involving computers
* **GDPR Art. 32** — Security of processing
* **UK Computer Misuse Act 1990**
* **Canada Criminal Code § 342.1** — Unauthorized use of a computer

---

## 8. See also

* `apps/accounts/legacy_hashes/VENDOR_COVERAGE.md` — strictness
  matrix per vendor (FACTS / Skyward NO write-blocked)
* `docs/SECURITY_KEYS.md` — encryption keys runbook
* `docs/DPA_TEMPLATE.md` — GDPR Art. 28 data-processing agreement
* `docs/DSAR_RUNBOOK.md` — data-subject access request 30-day SLA
* `companion-extension/src/vendors/facts.ts`,
  `companion-extension/src/vendors/skyward.ts` — extractor source
  (read-path safe-DOM, `// honest-stub:` on writes)
