# Fix: `recommended_sectors` column missing (production logs)

## Symptom

```
column siteconfig_workflowpack.recommended_sectors does not exist
column siteconfig_dashboardpack.recommended_sectors does not exist
```

## Fix

Apply Django migrations (includes `siteconfig` migration `0159_add_workflow_dashboard_recommended_sectors`):

```bash
python manage.py migrate siteconfig
# or full migrate
python manage.py migrate
```

Redeploy after migrate on Render (release command or shell).
