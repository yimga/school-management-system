# Form/view refactor guide — SiteSettings.get_solo() → runtime helpers

**Purpose:** Replace direct `SiteSettings.get_solo()` in tenant-facing views/forms with runtime-backed helpers so behavior is policy-driven and tenant-scoped. Complete "our part" so that when you touch a file, you follow this pattern.

**Reference:** PLAN_COMPLIANCE Phase 5–8; `apps/platform_runtime/helpers.py`; SITESETTINGS_AUDIT.md.

---

## When to use which helper

| You need | Use | Notes |
|----------|-----|--------|
| Site/school display name | `get_site_display_name(request)` | Replaces `SiteSettings.get_solo().site_name` in templates/context. |
| Branding (logo, tagline) | `get_effective_branding(request)` | Replaces branding from SiteSettings when only display is needed. |
| Backend feature flags | `get_effective_flags(request)` | Replaces `SiteSettings.get_solo().backend_feature_flags`. |
| Dashboard config for role | `get_effective_dashboard(request, role=...)` | Replaces legacy dashboard resolution. |
| Policy slice (e.g. admissions) | `get_effective_policy(request, module_name="admissions")` | When you only need a policy section. |
| Locale/terminology | `get_effective_locale(request)` | Replaces locale from SiteSettings. |

---

## Pattern (request available)

```python
# Before
from apps.siteconfig.models import SiteSettings
def my_view(request):
    site = SiteSettings.get_solo()
    return render(request, "x.html", {"site_name": site.site_name or "School"})

# After
from apps.platform_runtime.helpers import get_site_display_name
def my_view(request):
    return render(request, "x.html", {"site_name": get_site_display_name(request)})
```

When you need **multiple** SiteSettings fields (e.g. `school_code`, `company_email`, `portal_quick_actions`), keep `SiteSettings.get_solo()` until runtime is extended with those keys, or add a single helper that returns a minimal struct from runtime + fallback to get_solo() for the rest.

---

## Where request is not available

In **models**, **tasks**, **signals**, or **management commands**, you often don't have `request`. Options:

1. **Pass school_id or tenant context** and resolve runtime via `build_tenant_runtime(tenant_ctx, request=None)` then read from runtime (e.g. `runtime.branding`, `runtime.flags`).
2. **Keep SiteSettings.get_solo()** in those code paths and document with a short comment: `# No request; use get_solo() until job/signal gets tenant_ctx.`

---

## Per-app refactor order

1. **Portal** — High traffic; refactor site_name and flags first (see refactored slice in portal/views.py).
2. **Finance** — Use `get_effective_flags(request)` and `get_site_display_name(request)` where only those are needed.
3. **Evals** — Same; replace flags and site_name where request is available.
4. **Accounts** — Login/context processors: use get_site_display_name for display.
5. **Reports, dashboard, siteconfig** — Same pattern; extend runtime with more keys as needed.

Run `python scripts/lint_tenant_settings.py` after refactors to catch remaining get_solo() in tenant apps.

---

## Done when

- [x] This guide exists.
- [x] At least one slice refactored (portal: site_name in _whatsapp_invite_link and my_digital_id).
- [ ] Remaining tenant-facing views/forms refactored when touching (no big-bang; do as you go).
