# Plan XV: Wildcard SSL and CDN

## Wildcard SSL

For multi-tenant subdomains (e.g. `*.runmycampus.com`):

- **Let's Encrypt**: Use DNS-01 challenge for wildcard certs (e.g. `certbot certonly --manual -d "*.runmycampus.com" -d runmycampus.com`). Store certs in a path referenced by your reverse proxy (Caddy, Nginx, or Render).
- **Caddy**: Automatically obtains and renews certs; configure `*.yourdomain.com` in Caddyfile so each tenant subdomain is served with a valid cert.
- **Render / Cloudflare**: If using a proxy in front of the app, terminate SSL at the proxy and use their wildcard or per-hostname certs.

## CDN

- **Static assets**: Serve `/static/` and `/media/` via a CDN (e.g. CloudFront, Cloudflare) by setting `STATIC_URL` / `MEDIA_URL` to the CDN origin, or using WhiteNoise with a CDN in front.
- **Optional cache headers**: Set long `Cache-Control` for hashed static files; short or no-store for tenant-specific media.
- **Queue routing / autoscaling**: Use the platform’s worker/queue (e.g. Celery on Render, Redis) and scale workers by queue depth; document in your runbook.

## Checklist

- [ ] Wildcard or per-tenant SSL certificate configured at reverse proxy
- [ ] Static/media URLs point to CDN when in production
- [ ] Celery workers and beat scheduled per `CELERY_BEAT_SCHEDULE`
