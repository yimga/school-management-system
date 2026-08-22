# Edge TLS Runbook — choosing, issuing and changing a box's certificate

**Owner:** Edge / self-host · **Added:** 2026-08-22 · **Applies to:** every sovereign
box (`deploy/selfhost/`), not the Render cloud.

This is a step in **edge onboarding**. Do it with the school, once, before go-live —
and revisit it whenever the school's network changes. The decision is theirs; this
runbook is what you put in front of them to make it.

---

## 1. Why a box needs a certificate at all

A box reached at `http://10.10.20.137:10000` works. Login works, the dashboards work,
sync works. One thing does not, and cannot:

> **"Make this device offline ready"** asks for a PIN, then answers
> **"Local access could not be enabled on this browser."**

That message named the wrong culprit. The offline capability vault derives its PIN key
with `crypto.subtle`, and browsers expose WebCrypto **only in a secure context** —
HTTPS, or `localhost`. A plain-HTTP LAN origin is not one. Chrome implements WebCrypto
correctly; the *origin* does not qualify, so **changing browsers can never help**, and
no application-side change can either. Because sealing could never succeed,
`loadSealed()` was always null and *"Continue in local mode"* stayed hidden — **offline
continuity has never worked on any plain-HTTP box.**

That is the entire reason this runbook exists. Everything below is about getting the
box a certificate the school's devices will accept.

---

## 2. The four modes

Set **one** value in `deploy/selfhost/.env`:

```ini
RMC_EDGE_TLS_MODE=off | selfsigned | provided | acme
```

| Mode | Needs | Device work | Renewal | Choose it when |
|---|---|---|---|---|
| `off` | nothing | none | n/a | The school accepts no offline/local mode, today. |
| `selfsigned` | nothing | install the box CA once per device | you, every ~2 years | **No internet, no domain, no budget.** The only option that works on an island LAN. |
| `provided` (alias `ca`) | cert + key from any CA | none on managed devices | the school's CA | The district / ministry already runs a CA, or the school bought a certificate. |
| `acme` | public DNS name + inbound reachability | none anywhere | automatic | The box has a real hostname on the internet. |

`ca` is an accepted spelling of `provided`, because a certificate *from a certificate
authority* arrives as files. `acme` is a *protocol* for getting one automatically, not
a different kind of authority.

**Gilead Tech High runs `selfsigned`** — no public DNS name, LAN-only, and the school
should not wait on a registrar to get offline mode working.

---

## 3. What the school is actually agreeing to

Read these aloud. They are the parts people discover later and resent.

**`selfsigned`** — every device that browses the box must install the **box CA** once,
or click through a red warning every time. Click-through is not a neutral fallback: it
teaches a whole staff to dismiss certificate warnings, which is worse than plain HTTP
in a school with any laptop that also leaves the building. Budget 5 minutes per device,
once. Android and iOS each need a different gesture (§5).

**`provided`** — the school owns renewal. Nothing on an offline box can renew a
certificate for you, and an expired certificate is a *harder* outage than plain HTTP:
every browser refuses outright, including the tablets in the exam hall. Put the expiry
date in the school calendar the day you install it. `check_edge_readiness` warns from
30 days out, but only if someone runs it.

**`acme`** — the box must be reachable from the public internet for the challenge.
Many sovereign deployments exist *precisely* to avoid that. Do not talk a school into
`acme` to save yourself a trust install.

---

## 4. The Gilead path — self-signed, start to finish

```bash
cd deploy/selfhost

# 1. Declare the decision and the names people will actually type.
#    IPs matter: they go into an IPAddress SAN. An IP placed in a DNS SAN is ignored
#    by every browser, which is the classic reason a hand-rolled LAN certificate
#    still shows a name-mismatch warning at the address on the sticker.
cat >> .env <<'EOF'
RMC_EDGE_TLS_MODE=selfsigned
RMC_EDGE_TLS_HOSTNAMES=gilead.school.lan,10.10.20.137
EOF

# 2. DELETE the four hand-set flags if they are still in .env. They now follow from
#    the mode, and leaving them pins the plain-HTTP posture onto an HTTPS box:
#      SECURE_SSL_REDIRECT / SESSION_COOKIE_SECURE / CSRF_COOKIE_SECURE / SECURE_HSTS_SECONDS

# 3. CSRF_TRUSTED_ORIGINS carries a SCHEME. Flip it, or the first POST after the
#    switch fails a referer check and login looks broken.
#      CSRF_TRUSTED_ORIGINS=https://gilead.school.lan,https://10.10.20.137

# 4. Mint the box CA and the leaf.
docker compose -f docker-compose.yml exec web \
  python manage.py edge_tls --issue-selfsigned

# 5. Render the terminator config for this exact box and start it.
docker compose -f docker-compose.yml exec web \
  python manage.py edge_tls --print-caddyfile > Caddyfile.edge
docker compose -f docker-compose.yml --profile tls up -d

# 6. Prove it.
docker compose -f docker-compose.yml exec web \
  python manage.py check_edge_readiness --strict
```

Then hand the school **`var/edge-tls/ca.crt`** — the CA, *not* the leaf — and §5.

`ca.key` never leaves the box. Whoever holds it can mint a certificate for **any**
name that every device trusting this CA will believe. It is the one file here that is
worth more than the box.

---

## 5. Installing the box CA on a device

| Platform | Where |
|---|---|
| Windows | double-click `ca.crt` → Install Certificate → **Local Machine** → Place in **Trusted Root Certification Authorities** |
| macOS | Keychain Access → System → drag `ca.crt` in → open it → Trust → *Always Trust* |
| iOS / iPadOS | mail or AirDrop the file → Settings → Profile Downloaded → Install → then **Settings → General → About → Certificate Trust Settings** and enable it (this second step is separate and is the one everyone misses) |
| Android | Settings → Security → Encryption & credentials → **Install a certificate → CA certificate** (not "VPN & app user certificate") |
| Chrome on Linux | `certutil -d sql:$HOME/.pki/nssdb -A -t "C,," -n rmc-edge -i ca.crt` |

Firefox keeps its own store on every platform: Settings → Privacy & Security →
Certificates → View Certificates → Authorities → Import.

---

## 6. Changing your mind later — in either direction

This is supported, and it is a **configuration** change, not a code change. Ask the
box for the steps from wherever it is now:

```bash
python manage.py edge_tls --plan-to ca        # self-signed -> a real CA
python manage.py edge_tls --plan-to off       # back to plain HTTP
```

Two ordering constraints the plan enforces, both of which bite silently:

**Going up (HTTP → HTTPS).** Change `CSRF_TRUSTED_ORIGINS` to `https://` **before**
the redirect goes on. And warn the school that everyone must **re-enrol offline PIN**:
local mode could never seal on the old origin, and to a browser `https://host` is a
different origin from `http://host` — nothing carries over.

**Going down (HTTPS → HTTP).** Set `SECURE_HSTS_SECONDS=0` and redeploy *first*, then
wait out any `max-age` already handed out. A browser that cached an HSTS header refuses
plain HTTP to that origin for the full year no matter what the server now sends, and
there is no server-side remedy — only per-device surgery.

This is why **`selfsigned` and `provided` ship with HSTS at 0** and only `acme` turns
it on. A `.lan` name or an IP is an origin a *different* box may hold next term;
pinning HTTPS onto it for a year turns a reversible decision into a one-way door.
`check_edge_readiness` FAILs if HSTS is ever set on a LAN certificate.

---

## 7. Reading the box's posture

```bash
python manage.py edge_tls           # mode, source, certificate, derived flags
python manage.py edge_tls --json    # same, machine-readable
```

It reports the mode *and where it came from*, whether the certificate on disk actually
asserts every address the box answers at, how many days remain, and whether the four
Django security flags agree with the mode. A disagreement is legal — an explicit env
var wins on purpose — but it is exactly how a box ends up with `Secure` cookies on a
plain-HTTP origin and a login that 302s forever with nothing in the log.

Re-issuing (`--issue-selfsigned --force`) **reuses the existing box CA**, so a box that
moves to a new IP or gains a hostname gets a new leaf without anyone touching the
devices again. Only a missing or expired `ca.key` forces a new CA — and with it, a
re-install everywhere.

---

## 8. What readiness will tell you

`check_edge_readiness` (advisory) / `--strict` (blocks go-live):

| Level | Finding |
|---|---|
| FAIL | `RMC_EDGE_TLS_MODE` is a spelling we do not recognise — the box fell back to plain HTTP while the runbook says HTTPS |
| FAIL | mode is `selfsigned`/`provided` but the certificate or key is missing |
| FAIL | the certificate does not assert an address the box answers at |
| FAIL | the certificate has expired |
| FAIL | a security flag disagrees with the mode in the lockout direction |
| FAIL | HSTS is set on a LAN certificate (irreversible) |
| WARN | expiry inside 30 days |
| WARN | TLS is off — offline PIN / local mode cannot be enabled on any browser |

---

## 9. Related

- `apps/schools/edge_tls.py` — the policy, and why the database is deliberately not a
  layer in this particular cascade
- `deploy/selfhost/Caddyfile.edge`, `docker-compose.yml` (`--profile tls`)
- `docs/EDGE_LAN_HOSTNAME_DNS.md` — getting a name onto the LAN in the first place
- `docs/EDGE_UPDATE_PIPELINE.md` — how a new build reaches the box
- `docs/EDGE_TOPOLOGY.md`
