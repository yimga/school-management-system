# N22 — RTL and regional UX (structural notes)

**SOT:** N22 remains **open** for full MENA/regional pack QA and sitewide RTL polish. This doc records **repo evidence** for the structural path.

## Data model

- **`RegionConfig.is_rtl`** (`siteconfig` migration `0106_add_regionconfig_is_rtl`) — per-region RTL flag.

## Template / context

- **`templates/portal_base.html`** — `<html … {% if is_rtl %} dir="rtl"{% endif %}>` when `is_rtl` is true in template context.
- **`apps/siteconfig/context_processors.py` — `region_settings()`** — builds `is_rtl` from:
  - effective policy `rtl` when `request.school` is set, else
  - `region.is_rtl`, overridden when **`get_tenant_locale(school)`** returns `is_rtl: True`.

## Tests

- **`apps/siteconfig/tests/test_n22_region_settings_rtl.py`** — `region_settings` exposes `is_rtl` when region is RTL-capable.

## Product depth (still open)

- Full **RTL QA** on high-traffic portal/backend flows; **regional packs** install path; **inclusive imagery** — see SOT N23 and backlog.
