# Production deployment checklist

Engineering-focused checklist for cutting a **RunMyCampus** release to production. Adapt per host (Render, VM, k8s). No new external services are required for a minimal cut.

## 1. Environment & secrets

| Variable / topic | Notes |
| --- | --- |
| `SECRET_KEY` | **Required** when `DEBUG=0`; see `config/settings.py` (`ImproperlyConfigured` if missing). |
| `DEBUG` | Set to `0` in production. |
| `ALLOWED_HOSTS` | Comma-separated; base domain and `.{base}` added from `MULTI_TENANT_BASE_DOMAIN` when unset. |
| `CSRF_TRUSTED_ORIGINS` | Set explicitly, or rely on `RENDER_EXTERNAL_HOSTNAME` on Render. Wildcard tenant origins are appended for the base domain in settings. |
| Database | `DATABASE_URL` or configured Django `DATABASES` — run migrations. |
| Static | Run `collectstatic` behind WhiteNoise or CDN as already integrated in settings. |

## 2. Build & migrate

```bash
python manage.py migrate --noinput
python manage.py collectstatic --noinput
```

## 3. Smoke (manual)

After deploy, as a tenant operator:

1. Login
2. Backend dashboard
3. CCC (manager) if in scope
4. Reports: scheduled hub + one evidence page
5. One student and one teacher record
6. Marketplace surface available to that role
7. Studio OS shell
8. `/siteconfig/billing/plan/` read-only plan page

## 4. Rollback

- Revert release artifact to previous image / commit.
- If migration incompatible: restore DB snapshot taken **before** migrate, then redeploy previous build (avoid down-migrating in place unless practiced).

## 5. Post-cut monitoring

- HTTP 5xx rate, Celery/worker queues if used, scheduled report job logs.
- No PII in application logs beyond existing structured logging contract.
