# GeoIP deployment guide (Wave 10 + 12)

RunMyCampus uses GeoIP **only** to detect a first-time visitor's country so the
marketing surface + signup form can render locally-relevant copy without
requiring an explicit pick. The IP itself is never logged, never stored, and
never sent to a third party (other than the local .mmdb lookup which is purely
in-process).

## Backends (pick one)

The active backend is selected by the `RMC_GEOIP_BACKEND` env var:

| Backend            | Setup cost | Latency | Notes |
|--------------------|------------|---------|-------|
| `noop` (default)   | Zero       | 0 ms    | No country detection from IP; chain falls back to Accept-Language. |
| `cloudflare`       | Zero (if behind Cloudflare) | 0 ms | Reads `CF-IPCountry` header that Cloudflare auto-injects. **Recommended** for Cloudflare-fronted deploys. |
| `x-country-code`   | Custom WAF / load balancer config | 0 ms | Reads a custom `X-Country-Code` header that ops can inject from any upstream. |
| `maxmind-lite2`    | One-time .mmdb download + scheduled refresh | < 1 ms | Pure-local lookup against a GeoLite2-Country.mmdb file. Requires `pip install geoip2`. |

## Recommended setup: Cloudflare (zero config)

If runmycampus.com is fronted by Cloudflare, just set:

```bash
export RMC_GEOIP_BACKEND=cloudflare
```

…and you're done. Every request comes with the `CF-IPCountry` header populated
with a 2-letter ISO country code (or `XX` for unknown). The lookup is **0 ms**
overhead — no upstream call, no file read.

## Alternative setup: MaxMind GeoLite2 (self-hosted .mmdb)

For deploys NOT behind Cloudflare (or for offline / air-gapped environments),
mount a MaxMind GeoLite2-Country.mmdb file and point the service at it.

### 1. Get a free MaxMind license key

1. Sign up at https://www.maxmind.com/en/geolite2/signup (free tier).
2. Go to **Account → Manage License Keys → Generate New License Key**.
3. Copy the key (you only see it once).

### 2. Download the .mmdb file

Use the shipped downloader (stdlib-only — no extra deps):

```bash
export MAXMIND_LICENSE_KEY=YOUR_KEY
export GEOIP_COUNTRY_DATABASE_PATH=/etc/geoip/GeoLite2-Country.mmdb
python scripts/download_geoip_mmdb.py
```

The script will:
- Verify the license key + destination path are writable
- Download the latest GeoLite2-Country.tar.gz
- Extract the .mmdb file
- Atomically replace the destination

Add `--check-only` to verify config without downloading (useful in CI).

### 3. Install the geoip2 reader

```bash
pip install geoip2
# or pin in requirements/base.txt: geoip2>=4.7,<5.0
```

### 4. Enable the backend

```bash
export RMC_GEOIP_BACKEND=maxmind-lite2
```

The reader caches the .mmdb file in-process at first lookup. Restart the
service (or trigger a Render redeploy) after refreshing the file.

### 5. Schedule weekly refresh

MaxMind updates GeoLite2 twice a week (Tuesday + Friday). Add a cron / Celery
beat / Render Cron Job entry:

```bash
# Mondays + Saturdays at 03:00 UTC
0 3 * * 1,6 /app/scripts/download_geoip_mmdb.py
```

Or for Render Cron Jobs (`render.yaml`):

```yaml
- type: cron
  name: refresh-geoip-mmdb
  env: python
  schedule: "0 3 * * 1,6"
  buildCommand: pip install -r requirements/base.txt
  startCommand: python scripts/download_geoip_mmdb.py
```

## Resolver chain (where GeoIP fits)

`apps.siteconfig.country_localization_service.resolve_country_for_request`
walks signals in this order:

1. `request.school.country_code` — multi-tenant context (tenant subdomain)
2. `request.session["onboarding_country_code"]` — public signup flow
3. `request.COOKIES["rmc_country"]` — long-lived UX preference
4. **GeoIP lookup** (the topic of this doc) — opt-in via `RMC_GEOIP_BACKEND`
5. `Accept-Language` header tail (e.g. `fr-CM` → `CM`)
6. `""` → falls through to generic country pack

So GeoIP is consulted **before** the Accept-Language fallback. This is
intentional — Accept-Language carries the user's UI-language preference
("English"), but the visitor's location is a stronger signal for the
school-system / currency / regulatory context we want to localize to.

## PII / privacy posture

- **The raw IP is never logged** by either the GeoIP backend or the resolver.
  The MaxMind lookup happens in-process; the IP only crosses a method boundary
  into the reader, never into a logger or DB row.
- **Country code is the only output.** No city, no region, no lat/lon — those
  are intentionally not requested even though MaxMind's enterprise tier
  supports them.
- **GeoLite2 is free and locally-hosted.** No data leaves your infrastructure.
- **The Cloudflare backend** uses an HTTP header Cloudflare already adds for
  every request — no additional data flow.

## Verifying it works

After enabling a backend, hit any page:

```bash
curl -i https://runmycampus.com/ -H "CF-IPCountry: NG"
# Then check the rendered HTML for `data-rmc-country="NG"` on the <body>.
```

Or run the smoke test:

```bash
python -c "
import os
os.environ['RMC_GEOIP_BACKEND'] = 'cloudflare'
from apps.siteconfig.geoip_country_lookup import lookup_country
class FakeReq:
    META = {'HTTP_CF_IPCOUNTRY': 'NG'}
print(lookup_country(FakeReq()))   # -> 'NG'
"
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Backend logs "geoip2 not installed; falling back to noop" | `pip install geoip2` not run | `pip install geoip2` in your build / requirements |
| Backend logs "GEOIP_COUNTRY_DATABASE_PATH is empty or file missing" | Env var not set, or .mmdb not downloaded | Run `python scripts/download_geoip_mmdb.py` and verify path |
| Country resolves to `""` on a Cloudflare-fronted deploy | Backend not set to `cloudflare` | `export RMC_GEOIP_BACKEND=cloudflare` |
| `CF-IPCountry` returns `XX` | Cloudflare couldn't geolocate (proxy/VPN visitor) | Expected — chain falls back to Accept-Language |
| Wrong country detected | Visitor on VPN / mobile carrier with wrong NAT egress | Expected — `rmc_country` cookie (operator opt-in) wins over GeoIP |
