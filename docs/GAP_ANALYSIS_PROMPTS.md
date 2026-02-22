# Gap Analysis Prompts (Phase Audit)

Run these in Composer/Agent for a full system audit (research-only or research-then-fix). Reference: plan Section 2.2.

---

**Master audit**
> Perform a Full System Audit. Scan for: (1) Data Leakage — views/services fetching without explicit tenant scope; (2) HTMX Dead Ends — hx-get/post whose target ID does not exist or view returns full page instead of partial; (3) Branding Gaps — templates hardcoding color/logo instead of BrandSettings context; (4) Missing Validations — onboarding/admission forms missing server-side validation or CSRF; (5) Error State Gaps — forms without clear hx-target for error messages.

---

**HTMX fragility**
> Audit all hx-get, hx-post, hx-target, hx-swap. Find hx-target IDs missing in template. Check OOB swaps (unique ID, consistently returned). Verify Delete/sensitive actions have hx-confirm.

---

**Ghost tenant (security)**
> Cross-tenant data leak analysis: find objects.all()/objects.get() without TenantManager or schema_context; ensure no URL allows resource by ID without verifying ID belongs to request.tenant.

---

**Offline recovery**
> Audit offline sync: if server returns 500 during sync, is data kept in IndexedDB and not deleted? Check ID collisions (e.g. client UUID for offline-created records).

---

**UX feedback**
> Find HTMX triggers without hx-indicator; form validation errors returned as HTML partial to correct error div; Design Studio auto-save visible to admin.

---

**Zero-hardcoding**
> Replace currency symbols, date formats, hardcoded hex/Tailwind, labels (Grade/Teacher/Student), and fetch('/api/...') with tenant/settings-driven or {% url %} / get_tenant_url().

---

**Verification:** After fixing a gap, add a test that reproduces the gap and proves the fix (e.g. tenant isolation test must fail when isolation is removed).
