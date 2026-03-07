# Blueprint alignment (marketing & public surface)

This doc states how the marketing and public website work aligns with the in-repo executable blueprint and with external reference blueprints. **No code lives in the external files; they are reference only.**

## External blueprint files (reference only)

Location: `C:\Users\yimga\Documents\HY_DOC_MAINPC\Docs for Others_Friends_family\Gilead Tech High\important doc\`

| File | Role |
|------|------|
| `RunMyCampus_Full_System_Architecture_Map_and_North_Star_Blueprint.md` | Full system architecture and north star; use for high-level alignment of public vs tenant vs manager surfaces. |
| `RunMyCampus_Master_Blueprint_SINGLE.md` | Master single-doc blueprint; use for feature and routing consistency. |
| `RunMyCampus_Codebase_Refactor_Map_and_Platform_Standardization_Plan.md` | Refactor and standardization; use for codebase and platform standards. |

These files are **not** edited by this repo. They inform architecture and product direction; implementation follows the in-repo blueprint and `config/public_urls.py` / `apps/schools/marketing_views.py` patterns.

## In-repo blueprint and routing

- **Executable plan:** [RUNMYCAMPUS_BLUEPRINT_FULL_EXECUTABLE_PLAN.md](RUNMYCAMPUS_BLUEPRINT_FULL_EXECUTABLE_PLAN.md) (and any SINGLE_PLAN references in the repo).
- **Public surface:** When the canonical domain (e.g. runmycampus.com) is served with `UrlConfSwitcherMiddleware` using `public_urls`, all marketing and discovery routes are defined in [config/public_urls.py](../config/public_urls.py). Marketing views live in [apps/schools/marketing_views.py](../apps/schools/marketing_views.py).
- **Conversion flows:** New public URLs or conversion flows (e.g. book-demo form, cookie policy, funnel events) stay within these patterns: add routes in `public_urls.py`, add view logic in `marketing_views.py` (or a small dedicated module), and use `MARKETING_*` settings for optional integrations (Calendly, webhook, analytics).

## Summary

- Marketing and public surface work aligns with the **in-repo** [RUNMYCAMPUS_BLUEPRINT_FULL_EXECUTABLE_PLAN.md](RUNMYCAMPUS_BLUEPRINT_FULL_EXECUTABLE_PLAN.md) and existing `public_urls` / `marketing_views` patterns.
- The three **external** blueprint files in `…\Gilead Tech High\important doc\` are referenced for architecture and north star only; no code is written to those paths from this repo.
