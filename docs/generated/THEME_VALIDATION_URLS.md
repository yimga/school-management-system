# Theme validation URLs (Light / Dark / System)

Use these after deploy or on local dev with `Host: manager.runmycampus.com` / tenant host.
Toggle theme from the user menu (Light / Dark / System) on each page.

## Manager control plane (highest priority)

| Surface | URL | What to check |
|--------|-----|----------------|
| Super dashboard | https://manager.runmycampus.com/super/ | Sidebar labels, hero text, cards |
| Super schools | https://manager.runmycampus.com/super/schools/ | Table text, filters, surface strip |
| Platform admin index | https://manager.runmycampus.com/admin/ | Hero, shortcut cards, app list |
| Admin changelist | https://manager.runmycampus.com/admin/schools/school/ | Breadcrumbs, table headers/cells, filters |
| Admin change form | https://manager.runmycampus.com/admin/schools/school/add/ | Labels, help text, field inputs |
| Config center | https://manager.runmycampus.com/configuration/ | Domain cards, nav |
| Studio | https://manager.runmycampus.com/studio/ | Rail, canvas chrome |

## Tenant portal (school host)

Replace `{tenant}` with your demo slug (e.g. `demo-school`).

| Surface | URL pattern |
|--------|-------------|
| Backend dashboard | http://localhost:8000/t/{tenant}/authentication/backend/ |
| Tenant admin | http://localhost:8000/t/{tenant}/admin/ |
| Parent portal | http://localhost:8000/t/{tenant}/authentication/parent/ |
| Teacher portal | http://localhost:8000/t/{tenant}/authentication/teacher/ |

## Public marketing (fixed cream palette — no theme toggle)

| Page | URL |
|------|-----|
| Home | https://runmycampus.com/ |
| Pricing | https://runmycampus.com/pricing/ |

## Local quick commands

```bash
python manage.py runserver 0.0.0.0:8000
# Automated gate bundle (render smoke covers manager rows above + Playwright theme toggle):
bash scripts/run_theme_visibility_gates.sh
# Or narrow:
python scripts/verify_theme_visibility_platform.py
python scripts/scan_main_content_text_utilities.py
```

After deploy, still do a **one-time human pass**: toggle Light / Dark / System on each manager row and confirm no invisible labels in the main column (automated smoke cannot catch every Unfold widget state).
