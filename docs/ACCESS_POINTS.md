# Access points and how to get to them

This app is multi-tenant. **Where you go depends on the host (domain) and path.** Middleware chooses the URL config: **public** (marketing/discovery), **tenant** (school backend), or **default** (single-tenant / legacy).

---

## 1. How routing works

- **Base / public host** (e.g. `runmycampus.com`, `www.runmycampus.com`, or `school-management-system-2kzk.onrender.com`):  
  Public URL config → marketing, discover, signup, support, verify. No school context.

- **Tenant host** (e.g. `gilead-school.runmycampus.com` or a verified custom domain):  
  Tenant URL config → full school backend (dashboard, academics, finance, portal, etc.).

- **Path-based tenant** (any host):  
  Paths like `/t/<school-slug>/...` can be used to reach a tenant’s backend (e.g. `/t/gilead-school/authentication/login/`).

- **Single-tenant / legacy**:  
  If there is only one tenant or no base domain, the **default** URL config (`config.urls`) is used and many public + tenant paths live under one host.

---

## 2. Public access (base domain / public host)

Use the **base domain** (e.g. `https://school-management-system-2kzk.onrender.com` or `https://runmycampus.com`).

| What | Path | How to get there |
|------|------|-------------------|
| **Marketing home** | `/` or `/marketing/` | Open base URL or go to `/marketing/`. |
| **Discover / find your school** | `/discover/` | “Find your school” / email-based discovery. |
| **School search** | `/find/` | Search by name/slug (e.g. `?q=gilead`). |
| **Verify (public hub)** | `/verify/` | Public verification hub. |
| **Support (public hub)** | `/support/` | Public support hub. |
| **Pricing** | `/pricing/` | Marketing pricing page. |
| **Product, solutions, etc.** | `/product/`, `/solutions/`, `/book-demo/`, etc. | Marketing pages. |
| **Sign up (new school)** | `/signup/` | School signup. |
| **Verify signup** | `/verify-signup/` | After signup email. |
| **Onboarding wizard** | `/onboard/` | Post-signup onboarding. |
| **Regional (e.g. Cameroon)** | `/cm/`, `/ca/` | Regional marketing. |
| **Health (load balancer)** | `/health/`, `/ready/`, `/status/` | No auth. |
| **Weather (header API)** | `/api/weather/context/` | JSON; no auth. |

On **public host**, `/` typically redirects: logged-in → dashboard redirect; not logged-in → marketing landing (or tenant login if single-tenant).

---

## 3. Tenant access (school backend)

Use the **tenant host** (subdomain or custom domain) or the **path-based** prefix.

### By subdomain

- **URL:** `https://<subdomain>.<base-domain>`  
  Example: `https://gilead-school.runmycampus.com`  
  Or on Render: often the same host with tenant resolved by middleware (if configured).

### By path prefix (if enabled)

- **URL:** `https://<any-host>/t/<school-slug>/`  
  Example: `https://school-management-system-2kzk.onrender.com/t/gilead-school/`

### Tenant paths (under tenant host or `/t/<slug>/`)

| What | Path | How to get there |
|------|------|-------------------|
| **Tenant home** | `/` | Redirects: logged-in → `accounts:redirect` (dashboard); not logged-in → login. |
| **Login** | `/authentication/login/` | School login. |
| **Logout** | `/authentication/logout/` | Logout. |
| **Backend dashboard** | `/backend/` or `accounts:backend_dashboard` | Main staff dashboard (redirect). |
| **Portal (parent/student)** | `/portal/` | Portal home; role-based. |
| **KB / Help centre** | `/kb/` | Knowledge base. |
| **Academics** | `/academics/` | Courses, sections, etc. |
| **Finance** | `/finance/` | Invoices, payments, etc. |
| **Reports** | `/reports/` | Reporting. |
| **Analytics** | `/analytics/` | Analytics. |
| **Communication** | `/communication/` | Announcements, etc. |
| **Compliance** | `/compliance/` | Compliance dashboard. |
| **Payroll** | `/payroll/` | Payroll. |
| **EMIS** | `/emis/` | EMIS. |
| **Requests** | `/requests/` | Access requests. |
| **Site config / customizer** | `/siteconfig/`, `/siteconfig/customizer/` | Theme, branding, settings. |
| **API Center** | `/api-center/` | Integration catalog, etc. |
| **Evals** | `/evals/` | Evaluations. |
| **Django Admin** | `/admin/` | Django admin (staff/superuser). |
| **API schema (admin)** | `/api/schema/`, `/api/schema/ui/` | OpenAPI schema; RBAC-protected. |
| **Super (multi-tenant admin)** | `/super/` | Super-admin: tenant list, provisioning, health. |

---

## 4. Super-admin (multi-tenant management)

- **Who:** Staff/superuser or roles with super access.  
- **Where:** Under tenant URL config at `/super/` (or on a “manager” host if configured).  
- **Paths:** e.g. `/super/` (dashboard), tenant provisioning, tenant health, switch-to-tenant.  
- **How to get there:** Log in as a user with super access, then go to `/super/` on a host that serves tenant URLs (or manager URLs).

---

## 5. LTI (external LMS)

- **Launch:** `/lti/launch/<tool_id>/`  
- **Callback:** `/lti/launch/<tool_id>/callback/`  
- **Services:** `/lti/service/<tool_id>/lineitems`, scores, results, memberships, deep-linking.  
- **JWKS:** `/lti/jwks.json`  
Used by LMS (e.g. Moodle) to launch and talk to the app; tenant is identified by LTI context / request.

---

## 6. Quick reference: “I want to…”

| Goal | Where to go |
|------|-------------|
| See marketing / sign up / pricing | Base domain → `/`, `/marketing/`, `/pricing/`, `/signup/`. |
| Find my school / log in | Base domain → `/discover/` or `/find/`; then pick school → tenant login. |
| Log in to my school | Tenant URL: `https://<school-subdomain>.<base>/authentication/login/` or `/t/<slug>/authentication/login/`. |
| Open staff dashboard | Tenant URL → `/backend/` or after login redirect. |
| Open parent/student portal | Tenant URL → `/portal/`. |
| Use help centre | Tenant URL → `/kb/`. |
| Manage tenants (super-admin) | Tenant/manager URL → `/super/`. |
| Check app health | Any → `/health/` or `/healthz/`. |

---

## 7. Environment / deployment

- **Base domain:** Set `MULTI_TENANT_BASE_DOMAIN` (e.g. `runmycampus.com`) so public vs tenant hosts are detected.  
- **Single tenant:** If only one school, going to `/` may redirect to that tenant’s login.  
- **Render / no custom domain:** With one host (e.g. `*.onrender.com`), the app may treat it as public; use **path-based** tenant URLs like `/t/gilead-school/` to reach a school backend.

See **RUNMYCAMPUS_DEPLOYMENT.md** for deployment and multi-tenant routing details.
