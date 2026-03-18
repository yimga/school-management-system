# World-class bar: interop + learning/types + Studio (Phase J)

Maps to **RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md §Phase J**.

## 44 — Clever/ClassLink–class district motion (world-class)

| Improvement | Gap closed |
|-------------|------------|
| **OneRoster academicSessions** | LMS/district tools expect terms; we only had classes/students/teachers/enrollments. |
| **Tenant interop hub** | No single place for URLs, token lifecycle, SSO + LTI discovery links. |
| **Roster CSV (staff)** | Marketing promised CSV; Bearer APIs alone are not ops-friendly. |
| **Token rotate** | World-class = rotate without DB admin; bounded ServiceIntegration. |
| **Clever/ClassLink** | Proprietary APIs require partnership; **equivalent** = OAuth2-style Bearer + OneRoster 1.1 pull + documented district steps (same motion as roster SSO glue). |

## 23–30 / 31–43 — Learning delivery + institution types (world-class)

| Improvement | Gap closed |
|-------------|------------|
| **Named catalog in repo** | "Partial" had no single registry for delivery modes + institution-type pack mapping. |
| **Super surface** | Operators need one screen next to Curriculum packs / Education systems. |

## Runtime + Studio (world-class)

| Improvement | Gap closed |
|-------------|------------|
| **Control-plane nav** | Interop + packs discoverable from same shell as One SIS, any LMS. |
| **Cross-links** | One SIS page points to learning-delivery catalog and tenant playbook pattern. |
| **Bearer alignment** | API accepts **every** active OneRoster-class integration token on the school (district hub + legacy sync) so token rotation does not orphan existing ETL until credentials are removed. |

## Phase J+ (beyond reach)

| Track | Shipped |
|-------|---------|
| **Webhooks** | Student/teacher/class save → signed POST to `roster_webhook_url`. |
| **Security** | Scopes, IP allowlist, audit log, per-token + IP rate limits, export profiles. |
| **OneRoster** | `orgs`, `courses`, `users`; synthetic roster flag. |
| **Hub** | Readiness grid, LTI wizard, SSO tips, district packet, partner checklist, institution wizard. |
| **Packs** | Runtime apply + ministry stub super page + Studio MD checklists. |
| **Metrics** | Prometheus `sms_oneroster_requests_total`. |

Tests: `python manage.py test apps.api.tests.test_oneroster_phase_j_plus`.

## 45 — Identity and access (SSO, federation) — world-class

**Definition (SOT):** Federation and SSO across **all segments** — staff backend, teachers, parents, students, super/control plane — not only one login surface.

| Shipped baseline (codebase) | Evidence |
|-----------------------------|----------|
| **OIDC** | `apps/accounts/views_oidc.py` — start/callback, ServiceIntegration OAUTH. |
| **SAML 2.0** | `apps/accounts/views_saml.py` — metadata, ACS, replay-aware logging per `public_endpoint_audit.md`. |
| **Login SSO discovery** | `_get_login_sso_integrations` — multiple IdPs on login. |
| **Tests** | `test_oidc_views`, `test_saml_views`. |

| Improvement (world-class) | Why |
|---------------------------|-----|
| **Segment-scoped IdP policies** | Staff vs parent vs student vs super: different allowed IdPs, forced SSO, and fallback rules (enterprise buys “parents Google-only”). |
| **JIT provisioning + account linking** | Map SAML `NameID` / OIDC `sub` to existing users; safe merge; block duplicate emails across federation. |
| **SCIM 2.0 inbound (full lifecycle)** | Create/update/deactivate users and group membership from Entra/Okta/Google; complements SSO (see optional replay hardening in audit §6). |
| **Session + step-up MFA** | High-value actions after SSO still require MFA where policy says so; session fixation and idle timeout per segment. |
| **IdP health dashboard** | **Shipped (v1):** Backend → District & LMS interop → **SSO / IdP login health** table (`FederationSsoHealth`); SAML ACS + OIDC callback update last OK / last fail / error summary. *Next: cert expiry alerts, metadata refresh job.* |
| **Enterprise IdP compatibility matrix** | Documented + tested: Microsoft Entra ID, Google Workspace, Okta, OneLogin, Keycloak patterns. |
| **Control-plane federation** | Super/admin SSO mandatory option for districts (separate from tenant SSO). |
| **Audit export** | Who logged in via which IdP, IP, user agent — aligns with trust center / compliance story. |

---

## 44 — Optionals and parity track (do not drop)

| Optional | Notes |
|----------|--------|
| **Clever API / ClassLink Roster Server (native)** | Partnership; district onboarding one-click; status: BLOCKED until vendor agreement — see `WEDGE_WORLD_CLASS_IMPLEMENTATION.md`. |
| **OneRoster delta / sync tokens** | Reduce full pulls; world-class at scale. |
| **OneRoster orgs / courses depth** | Full org hierarchy + course catalog parity with top districts. |
| **Webhook roster change events** | Push to RunMyCampus when district SIS changes (where vendor supports). |
| **Guided import → SIS** | UI: preview diff, dry-run, reconcile conflicts (merge vs overwrite per field). |
| **Multi-district / LEAs** | One operator, many child schools; roster scope per org (enterprise). |
| **LTI 1.3 tool JWT verification** | Full launch security per LTI spec; deferred in `public_endpoint_audit.md` §6 — required for “any LMS” hardening. |
| **AGS (Assignment and Grade Services)** | Grade passback depth beyond minimal launch. |
| **NRPS (Names and Role Provisioning)** | Dynamic roster in LMS from platform context. |
| **IP allowlist + per-token rate limit** | Already in OneRoster path; extend to all public interop surfaces consistently. |

---

## 45 — Optionals and parity track (do not drop)

| Optional | Notes |
|----------|--------|
| **OIDC RP-initiated logout + front-channel back-channel** | Clean sign-out across IdP + all app tabs. |
| **SAML metadata refresh job** | Auto-refresh signing certs from IdP metadata URL. |
| **Passwordless / passkeys as primary** | Already have passkey paths; align with “SSO first, passkey second” enterprise narrative. |
| **Risk-based login (impossible travel, etc.)** | Extend `security_audit` signals with IdP context. |
| **Group / role mapping from IdP** | Map SAML attributes / OIDC claims → Django groups / school roles (reduce manual RBAC). |
| **Guest / contractor access** | Time-bound federated accounts for auditors and vendors. |
| **FAPI / DPoP (financial-grade)** | For regulated customers requiring bound tokens. |

---

## 44 + 45 — Cross-wedge enterprise bar

| Theme | Improvements |
|-------|----------------|
| **Docs + runbooks** | Single “District onboarding” + “IdP onboarding” playbook (Clever-class + SAML/OIDC). |
| **Trust center** | Cards: interop status, SSO health, roster last sync, partnership roadmap (Clever/ClassLink). |
| **Contract tests** | CI: OIDC/SAML smoke, OneRoster contract slices (already partially in gate). |
| **Observability** | Metrics: `sms_oneroster_requests_total`, SSO success/failure by IdP, roster job duration. |

---

## Verification

- `python manage.py test apps.api.tests.test_oneroster_academic_sessions apps.accounts.tests.test_district_interop_hub apps.schools.tests.test_learning_delivery_packs_view -v 2`
- Manual: tenant **Backend → District & LMS interop** → rotate token → curl OneRoster with Bearer.
- SSO: exercise SAML metadata download + OIDC callback per tenant test IdP; see `test_saml_views`, `test_oidc_views`.
- `python manage.py test apps.accounts.tests.test_federation_sso_health -v 1`
