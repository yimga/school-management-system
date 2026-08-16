# Edge box — LAN hostname + local DNS

Give a self-hosted (edge) box a **stable LAN hostname** — e.g. `gilead-tech.school.lan` —
that resolves to the box's fixed LAN IP, so clients reach it by name. IP-only is
brittle: the address can move, browsers can't cleanly TLS a bare IP, and the app
(django-tenants) routes each tenant by hostname.

This is runbook step **`configure_lan_hostname`** (see `apps/lifecycle/edge_onboarding.py`).
It is the one prerequisite the platform does **not** provision for you — the name has
to resolve on your LAN, which is a router / DNS / hosts-file job.

---

## TL;DR — the working URL

The box is served over **plain HTTP** on its LAN port (default **10000**), with **no
TLS**. So:

```
✅  http://gilead-tech.school.lan:10000/authentication/login/
❌  https://gilead-tech.school.lan/…         ← no TLS on the box = the "no lock" / connection failure
❌  http://gilead-tech.school.lan/…          ← no port-80 proxy; the :10000 is required
```

**Reach the box RIGHT NOW, before any DNS setup**, straight by IP (works because
`SINGLE_TENANT` routes any host to the sole school):

```
http://<BOX_LAN_IP>:10000/          e.g.  http://10.10.20.137:10000/
```

`/` auto-redirects to `/authentication/login/`. If the IP URL works but the name
doesn't, the app is fine and the gap is **DNS** (below). If neither works, check the
box config (bottom of this doc).

---

## 1. Fix the box's IP first

DNS is pointless if the box's address drifts. Reserve it on the router:
**DHCP reservation** binding the box's MAC to a fixed lease (e.g. `10.10.20.137`),
or set a static IP on the box. Everything below maps the name to *that* address.

## 2. Map the name → the box IP (pick one by LAN size)

| Method | Best when | Reach |
|---|---|---|
| **Router DNS / host entry** | Router supports custom DNS (OpenWrt, pfSense, many prosumer) | Every LAN client automatically — cleanest |
| **Pi-hole / dnsmasq on the box** | You want whole-LAN control + logging / ad-block | All clients once the router hands out the box as DNS |
| **Per-client hosts file** | A handful of fixed machines, fast test | Only the edited devices — phones/tablets left out |

### a. Router DNS / host entry
Add a local DNS record (a "host override" / "DNS host entry") on the router:
`gilead-tech.school.lan → <BOX_LAN_IP>`. Every device that uses the router for DNS
resolves it automatically. Exact menu varies (OpenWrt: *Network → DHCP and DNS →
Hostnames*; pfSense: *Services → DNS Resolver → Host Overrides*).

### b. Pi-hole / dnsmasq on the box
```bash
echo 'address=/gilead-tech.school.lan/<BOX_LAN_IP>' | sudo tee /etc/dnsmasq.d/rmc-edge.conf
sudo systemctl restart dnsmasq
# then point the router's DHCP "DNS server" at the box's IP so all clients use it
```
(Pi-hole: add the same record under *Local DNS → DNS Records*.)

### c. Per-client hosts file (fast test)
```bash
# Linux / macOS
echo '<BOX_LAN_IP>  gilead-tech.school.lan' | sudo tee -a /etc/hosts
```
```
# Windows (edit as Administrator):
#   C:\Windows\System32\drivers\etc\hosts
<BOX_LAN_IP>  gilead-tech.school.lan
```

### Verify it resolves to the box
```bash
getent hosts gilead-tech.school.lan     # Linux — must print <BOX_LAN_IP>
ping gilead-tech.school.lan             # any OS — must reply from <BOX_LAN_IP>
```
Then open: `http://gilead-tech.school.lan:10000/authentication/login/`

---

## 3. Box config that must be set (so the host is accepted, not 400'd)

On an edge box in RLS single-schema mode, these env vars make `gilead-tech.school.lan`
resolve to the Gilead tenant and be accepted by Django (mirrors
`deploy/selfhost/.env.edge.example`):

```dotenv
USE_DJANGO_TENANTS=0                 # RLS single-schema
SINGLE_TENANT=True                   # any LAN host → the sole active school
MULTI_TENANT_BASE_DOMAIN=school.lan  # injects the ".school.lan" wildcard into ALLOWED_HOSTS
ALLOWED_HOSTS=localhost,127.0.0.1,school.lan,gilead-tech.school.lan,<BOX_LAN_IP>
CSRF_TRUSTED_ORIGINS=http://gilead-tech.school.lan:10000,http://<BOX_LAN_IP>:10000
WEB_PORT=10000
DEBUG=0

# THE LAN-HTTP LOGIN BREAKERS — all must be 0 on a plain-HTTP box, or "secure"
# cookies never round-trip over HTTP and login silently 302-bounces in a loop:
SECURE_SSL_REDIRECT=0
SESSION_COOKIE_SECURE=0
CSRF_COOKIE_SECURE=0
SECURE_HSTS_SECONDS=0
```

Why each matters:
- **`MULTI_TENANT_BASE_DOMAIN=school.lan`** — the ALLOWED_HOSTS default covers `.local`,
  **not** `.lan`. Setting this appends a leading-dot `.school.lan` wildcard so any
  `*.school.lan` host is accepted; without it, `gilead-tech.school.lan` returns
  **400 Bad Request** at `DEBUG=0`.
- **`SINGLE_TENANT=True`** — routes any reaching host (name **or** IP) to the one active
  school, so you don't have to bind a per-host domain. (If you ever turn this off, set
  `School.subdomain="gilead-tech"` to match the `gilead-tech.school.lan` label, or
  register a verified `SchoolDomain` row for the exact FQDN.)
- **The four secure-cookie flags = 0** — the single most common "I can't log in" cause
  on a LAN box. `check_edge_readiness` flags this as the *plain-HTTP-over-LAN
  secure-cookie trap*.

Validate the box side any time with:
```bash
python manage.py check_edge_readiness --strict
```

---

## Want the browser lock + a clean `https://gilead-tech.school.lan` (no port)?

The shipped edge stack has **no TLS terminator and no port-80 proxy** — gunicorn binds
plain HTTP on 10000. To get a padlock and drop the `:10000`, front the box with your own
reverse proxy (**Caddy** or **nginx**) that terminates TLS with a **local CA** cert for
`*.school.lan` and proxies `:443 → 127.0.0.1:10000`. Then flip the four secure-cookie
flags back to `1`. That is optional polish; plain `http://…:10000` is fully functional on
a trusted LAN.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "no lock" / can't connect on `https://` | Box has no TLS | Use `http://…:10000` |
| Connects on IP, not on the name | DNS not resolving | Do step 2; `getent hosts <name>` must print the box IP |
| **400 Bad Request** | Host not in ALLOWED_HOSTS | Set `MULTI_TENANT_BASE_DOMAIN=school.lan` (+ list the host) |
| Login page loads but keeps bouncing to itself | Secure cookies over HTTP | Set the four `*_SECURE` / `SSL_REDIRECT` / `HSTS` flags to `0` |
| Name works but "Campus Not Found" | Multi-tenant on + no match | Set `SINGLE_TENANT=True`, or make `School.subdomain` match the host label |
