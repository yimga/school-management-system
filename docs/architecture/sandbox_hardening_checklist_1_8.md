# Sandbox hardening checklist (Section 1.8)

**Purpose:** Document and implement sandbox security for embedded/iframe experiences (e.g. marketplace apps, widgets) so the platform is safe when third-party or first-party code runs in a sandbox.

**Reference:** REMAINING_PLAN_AUDIT_GAPS 1.8; INCOMPLETE_ITEMS_AND_NORTH_STAR_ALIGNMENT; RUNMYCAMPUS_CONSOLIDATED_ARCHITECTURE_AND_REFACTOR Part B.

---

## Checklist

| Item | Status | Where / done when |
|------|--------|--------------------|
| CSP (Content-Security-Policy) for sandbox/embed pages | **Done** | `apps/marketplace/views.sandbox_embed`: sets `Content-Security-Policy` (default-src, script-src, style-src, frame-src, frame-ancestors). Also `apps/schools/marketing_views` app sandbox placeholder. |
| postMessage contract | **Document** | Allowed origins, message types, payload schema — see “postMessage contract (example)” below in this doc. |
| Embed points | **List** | `/siteconfig/app-sandbox/?app_slug=...&widget_id=...` (marketplace_sandbox_embed); dashboard widgets load iframe from widget config; public app sandbox placeholder (marketing_views). |
| Sandbox iframe attribute | **Done** | `sandbox_embed`: iframe has `sandbox="sandbox allow-scripts allow-same-origin"`. |
| No sensitive data in postMessage | Audit | When postMessage is implemented: only non-sensitive identifiers and scoped tokens. |

---

## postMessage contract (example)

- **Parent → embed:** `{ type: "ready" }`; `{ type: "context", tenantId, schoolId, role }` (non-sensitive identifiers only).
- **Embed → parent:** `{ type: "resize", height }`; `{ type: "navigate", path }` (optional; validate path).
- **Origins:** Only allowlisted manager/tenant origins; reject others.

---

## Done when

- [x] Sandbox hardening checklist doc created (this file).
- [x] CSP and sandbox attribute implemented for live embed: `apps/marketplace/views.sandbox_embed` (app-sandbox). Embed points and postMessage contract documented in this doc. Origin checks: frame-ancestors set from widget URL origin when iframe_src is external.
