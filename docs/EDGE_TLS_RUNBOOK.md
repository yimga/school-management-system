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

## 4. One command

Everything in section 4b is performed, in the only correct order, by:

```bash
bash deploy/selfhost/edge-bootstrap.sh
```

That is the whole of it. There is nothing to decide first and nothing to set in the
environment. Safe to run again, any number of times: on a box that is already correct
it changes nothing and says so. It ends by printing the URL devices should be sent to.

**The backup passphrase generates itself.** It used to be a hard stop — set
`RMC_EDGE_TLS_CA_PASSPHRASE` or the script refused — and that was the wrong trade. A
secret invented at a console in a school office is either weak or lost by the time it
is needed, and both of those end with a box whose CA cannot be restored. So when the
variable is unset the script generates 44 random characters, writes them
owner-only to `box-ca-passphrase.txt` beside the bundle, and **reuses that file on
every later run** rather than re-encrypting the bundle under a second passphrase.

Set `RMC_EDGE_TLS_CA_PASSPHRASE` yourself and nothing is generated or written. Point
`RMC_EDGE_CA_PASSPHRASE_FILE` somewhere else — a mounted secrets volume — and it goes
there instead. Either way it is read from the environment and never passed as a flag:
a command line is visible in `ps`, in shell history and in docker's own event log.

> The generated file starts life **next to the bundle it protects**, which is not
> where it should stay: together in one place, the encryption bought you nothing. The
> script's closing notes name both paths and ask you to move one. That is a real
> remaining task, not a formality — but a box with a backup whose passphrase is
> sitting beside it is strictly better than the box with no backup that the hard stop
> was producing.

**Where it writes.** `box-ca-bundle.p12` (the encrypted CA backup, which carries the
PRIVATE KEY), `box-ca.crt` (the public CA), `box-ca-passphrase.txt` and the `mdm/`
folder all land in the repo's **parent** — `/srv` on a stock box, beside `/srv/rmc`.
Override with `RMC_EDGE_OUT_DIR=/some/path`.

> **This default changed.** It used to be the repo itself. `$REPO` is a git working
> tree on every box, so a CA private key sat one `git add -A` away from a public
> remote with nothing in `.gitignore` to stop it. Both filenames are now gitignored
> as a second lock. If you bootstrapped a box before this change, look for
> `box-ca-bundle.p12` **inside** the checkout and move it out.

**Use this rather than the manual steps.** Four of those steps are ordering traps —
each one correct in isolation, the sequence wrong, and the result invisible until
thirty devices have been touched. They are not documentation problems, so they are
not solved by documentation:

| The mistake | What now happens |
|---|---|
| Render the terminator config before the certificate exists | `edge_tls --print-caddyfile` **refuses**. It would emit `tls internal` — Caddy's own CA — so the `ca.crt` you distribute matches nothing the box presents. |
| Issue on a box whose certificate volume was lost | **Refused**, including by the unattended boot-time `--ensure`. The box records its CA fingerprint in a *different volume*, so it can tell a first install from a loss. |
| Install the CA on devices before backing it up | The bootstrap exports and **reads the bundle back** before it reports success. An unverified backup is a belief. |
| Back the CA up into the certificate directory | **Refused before the file is written**, not reported afterwards — by then the step is ticked off and the operator has walked away. |
| Reissue and forget to restart the terminator | Detected: the box compares what is **served** against what is on disk and names both. |
| Pin `SECURE_SSL_REDIRECT` and friends in `.env` | Readiness warns whenever they are set by hand at all — not only when they currently disagree. They will not follow the next mode change. |

**It also writes the management-console payloads, every run.** `mdm/` lands beside
the bundle and holds `box-ca.mobileconfig`, `box-ca.crt`, `android-policy.json` and a
README naming the fingerprint. That used to be a separate command
(`edge_tls --export-mdm`), which is a command nobody remembers exists — and the cost
of not remembering is a school that could have pushed the CA to every device from one
console walking the building instead. It still exists for a box being brought up by
hand; see 5c.

What the machine *cannot* do is the part that genuinely needs a person: moving the
bundle (or the passphrase) off the box, and re-enrolling offline PIN at the new
origin. The script ends by listing exactly those two and nothing else. Installing the
CA on devices used to be on that list; on Windows, macOS and Linux it is now one
paste, and on a managed fleet it is one console push — see 5b-i and 5c.

### Checking a box without changing it

```bash
docker compose -f deploy/selfhost/docker-compose.yml exec web \
  python manage.py edge_bootstrap --dry-run

docker compose -f deploy/selfhost/docker-compose.yml exec web \
  python manage.py edge_tls --check-terminator
```

---

## 4b. The Gilead path — self-signed, start to finish

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

### 5a. Send devices to a URL, not a file

The box publishes its own certificate authority. `edge-bootstrap.sh` prints the
address at the end of its run; it is the box's own, on the app port:

```
http://<box>:10000/edge/trust/
```

Ask for it at any time — no bootstrap run needed. This prints the URL and nothing
else, so it is safe in a script:

```
docker compose -f deploy/selfhost/docker-compose.yml \
  exec -T web python manage.py edge_tls --trust-url
```

One computation, four surfaces. The bootstrap banner, `edge_bootstrap`, `edge_tls`
and the onboarding wizard's generated runbook all read the same helper, so the
address on a printout and the address in a terminal cannot disagree. It picks a DNS
name over an IP where the box has one — the leaf can be reissued onto a new address
without revisiting a device, but only if what people wrote down was a name — and it
prints nothing at all rather than a URL with a hole in it when the box holds no
reachable address.

That page shows the fingerprint, a QR code so a phone does not have to type an IP,
the certificate itself, and the per-platform step below for whichever device is
looking at it. Nobody copies a file off the box and nobody carries one around.

**It is plain HTTP, deliberately.** A device reaches this page precisely because it
does not trust the box yet, so redirecting it to HTTPS shows the very warning it
came to fix — and people who are taught to click through a warning keep doing it.
`^edge/trust/` is in `SECURE_REDIRECT_EXEMPT` for that reason and no other.

**Two layers have to agree about that, and for a while only one did.** Django's
exemption governs the app; the terminator sits above it, and the `:80` block that
sends everyone to HTTPS was redirecting the trust page too. Measured on a live box:
`http://<box>/edge/trust/` answered `302` to `https://<box>/edge/trust/`, which is
the certificate warning, on the address people actually type. Neither layer was
wrong on its own, which is why nothing caught it. The rendered `:80` block now
serves `/edge/trust/` by proxy and redirects everything else.

So the bare address works:

```
http://<box>/edge/trust/
```

**`--trust-url` still prints the `:10000` form, and that is not an oversight.** The
`:80` block is only rendered where the box serves a key pair of its own — the
common case, and the only one where a trust page means anything. A box on `acme`
needs port 80 for its own challenge and has a publicly trusted certificate, so it
has nothing to enrol; a box still on `tls internal` is presenting a certificate
this page's CA did not sign. The app port answers in every one of those states, so
that is what the tooling prints and what belongs on a printout. Use the bare
address when you are typing it yourself.

**Have someone check the fingerprint.** A certificate authority you install can
vouch for any site, and over plain HTTP another machine on the LAN could answer in
the box's place and offer its own. Code cannot close that; a person comparing two
numbers can, and it takes five seconds.

On the box console, `manage.py edge_tls` prints it under **Trust anchor**:

```
Trust anchor (this is what devices install)
  subject      CN=RunMyCampus Edge CA (gilead-tech.local),O=RunMyCampus Edge
  expires      2036-08-23T15:41:19+00:00 (3649 days)
  fingerprint  92:FA:BB:5A:...:09:A6
  Devices install it at http://gilead-tech.local:10000/edge/trust/
```

That is the **CA's** fingerprint, deliberately, and not the leaf's above it. Devices
install the CA; the leaf is reissued underneath it every time the box changes
address, so a leaf fingerprint would stop matching the moment DHCP moved the box and
the page would start crying wolf.

Only the CA is served. The private key is not reachable from any route: the view
reads one path from `certificate_paths()` and takes nothing from the request.
`box-ca-bundle.p12` — which *does* carry the private key — is written outside the
repo, is gitignored, and is never offered over HTTP.

The page 404s anywhere that is not a sovereign box, so the cloud never serves
something calling itself a certificate authority.

**It answers even when the school does not resolve.** `/edge/trust/` is skipped by
both school-resolving middlewares, the way `/health` is. Without that, a box that has
just booted, is still migrating, or has no school row yet answers a device with a
redirect to `https://<base-domain>/school-not-found/` — which, on a school LAN with
no route to the internet, is a browser error rather than a page. The one surface that
has to survive a half-configured box was the one that did not.

**The address handed out is never the platform's.** `config/settings.py` appends the
canonical domain and its wildcard to `ALLOWED_HOSTS` on *every* deployment, a box
included, so the public domain sits in a box's own address list looking exactly like
a school's hostname. It is excluded explicitly: a device sent there either has no
route off the LAN, or reaches the cloud, which 404s this page by design.

**If that URL shows a marketing page, the box is on the wrong urlconf.** `/edge/trust/`
is declared only in `config/tenant_urls.py`. On the developer urlconf it matches an
unrelated two-segment locale route as `language=edge, country=trust` and renders a
regional landing page -- so a device gets a *website* rather than an error, and the
person assumes they are in the right place and hunts for a download button that is
not there. That symptom means one thing: this box is not being recognised as a box.
`check_edge_readiness` already FAILs on it with *"a bare-IP host still routes to
config.urls"*; fix that and the page appears.

### 5a-i. When the box's IP changes

It will. DHCP hands out a new lease, a room gets re-cabled, the box moves campus.

**Devices already enrolled need nothing.** They trust the *CA*, not the address, and
`ensure_certificate` reissues the leaf onto the new address while reusing the CA on
disk. That is the whole reason the box mints two certificates instead of one.

**What changes is where a NEW device goes to enrol** — and only if this box is
reached by an IP. Ask, rather than remembering:

```
docker compose -f deploy/selfhost/docker-compose.yml \
  exec -T web python manage.py edge_tls --trust-url
```

`check_edge_readiness` reports it too, and grades it:

| It says | Meaning |
|---|---|
| `[OK] ... — a NAME` | The URL survives any address change. Nothing printed goes stale. |
| `[WARN] ... — but that is an IP` | The CA is still fine and nobody is revisited, but every printout naming this URL is now wrong and the box gives no sign. |
| `[WARN] This box holds no address...` | Nothing to hand out at all — fix `RMC_EDGE_TLS_HOSTNAMES` or `ALLOWED_HOSTS`. |

The fix for the middle row is free and permanent: give the box a stable name. On a
LAN with no DNS server, mDNS `.local` is answered by the box itself and follows it to
any address on the segment — see docs/EDGE_LAN_HOSTNAME_DNS.md. A DHCP reservation
keyed to the box's MAC stops the address moving within a site at all.

### 5b. Where it lands on each platform

| Platform | Where |
|---|---|
| Windows | double-click `ca.crt` → Install Certificate → **Local Machine** → Place in **Trusted Root Certification Authorities** |
| macOS | Keychain Access → System → drag `ca.crt` in → open it → Trust → *Always Trust* |
| iOS / iPadOS | mail or AirDrop the file → Settings → Profile Downloaded → Install → then **Settings → General → About → Certificate Trust Settings** and enable it (this second step is separate and is the one everyone misses) |
| Android | Settings → Security → Encryption & credentials → **Install a certificate → CA certificate** (not "VPN & app user certificate") |
| Chrome on Linux | `certutil -d sql:$HOME/.pki/nssdb -A -t "C,," -n rmc-edge -i ca.crt` |
| Chromebook, **managed** | nobody sitting at the device can do this. Push it: Google Admin → Devices → Networks → Certificates, scoped to the org unit, with *Use this certificate as an HTTPS certificate authority* ticked |
| Chromebook, personal | Settings → Privacy and security → Security → Manage certificates → Authorities → Import |

Firefox keeps its own store on every platform: Settings → Privacy & Security →
Certificates → View Certificates → Authorities → Import.

Two of these rows decide whether a rollout is an afternoon or a fortnight, so check
them **before** promising a date:

- **Managed Chromebooks and managed iPads cannot be done device by device.** The
  install is an admin-console push, and whoever holds that console may not be in the
  same building or the same organisation. A school on a managed fleet with no
  console access cannot use a box-minted CA at all — it needs `provided` mode with a
  certificate from a CA the fleet already trusts.
- **Android 11 and later put a user-installed CA in a store that apps ignore.**
  Browsers honour it, so the web app is fine; a native app pointed at the box is
  not, and that difference will be reported as "it works on my phone but not in the
  app".

Both of those rows stop being hard if the school manages its devices — see 5c.

---

### 5b-i. On a computer, it is one paste

The table above is what the OS makes you do by hand. The trust page does not ask
anyone to do it by hand: on Windows, macOS and Linux it renders a single command for
that platform, with the box's own fingerprint compiled into it. The command fetches
the certificate, computes its SHA-256, compares it against that literal, and installs
**only** on a match.

That is worth being precise about, because it is easy to read as more than it is.

- **What it removes** is every way this goes wrong that is not an attacker: the wrong
  store (the single commonest failure — Windows defaults to the *user* store, where
  Chrome and Edge do not look), a truncated download, yesterday's `ca.crt` still in
  Downloads from before the box was rebuilt, the wrong box on a site that has two.
- **What it does not remove** is the reason section 5a asks you to check the
  fingerprint against the console. A page that lied about the certificate would lie
  about the literal beside it too. The comparison a person makes against
  `manage.py edge_tls` is still the only thing standing between a school and somebody
  else's certificate authority, and no command can make it for you.

**Nothing fetched is ever executed.** The page could have offered a downloadable
installer and saved another step; it does not, and that is the design rather than an
omission. This page is served over plain http on a school LAN — that is load-bearing,
see 5a — and a page that told a device to run whatever the box sent would escalate a
LAN attacker from *your trust store* to *your machine*. A command that only ever
installs a fingerprint-checked certificate cannot do that however the page is
answered.

Administrator / `sudo` is still required and always will be. Writing the machine-wide
root store is exactly the thing every OS reserves for an administrator, and a web page
is never going to be granted it.

Firefox keeps its own certificate store on every platform, and Chrome does too on
Linux. A browser that still warns after one of these commands succeeded is not
evidence that it failed.

---

### 5c. Managed fleets — the box builds the payload

If the school manages its devices, **nobody performs 5a or 5b at all**. Every console
can install a root CA on every enrolled device at once, and on Apple hardware a
*pushed* profile is trusted on arrival: the Certificate Trust Settings screen that
everybody misses exists only for hand-installed certificates.

The box generates what each console wants, from its own CA:

```
docker compose -f deploy/selfhost/docker-compose.yml exec web \
  python manage.py edge_tls --export-mdm /app/var/mdm
```

| File | Console |
|---|---|
| `box-ca.mobileconfig` | Jamf, Mosyle, Kandji, Intune, Apple Configurator |
| `box-ca.crt` | Google Admin (ChromeOS / Chrome), Intune *Trusted certificate* profile, Group Policy |
| `android-policy.json` | the `caCerts` fragment for an Android Management API policy |
| `README.txt` | what each file is for, **with the fingerprint printed in it** |

The profile is also served straight off the box at
`/edge/trust/box-ca.mobileconfig`, and the trust page offers it as the primary
download to any Apple device that opens the page.

**The identifiers are derived from the CA fingerprint, deliberately.** Apple replaces
an installed profile when a new one carries the same `PayloadIdentifier`, and
installs a *second* one when it does not. So re-pushing after a box rebuild replaces,
while a genuinely new CA installs alongside and can be told apart. Random UUIDs would
have quietly accumulated another trust anchor on every device in the school on every
push.

**Do not write the export into the certificate directory** — the command refuses.
Everything it writes is public; `ca.key` sits in that directory and is not; and an
export folder is the thing most likely to be copied off the box wholesale.

Android is the row where this matters most. Since Android 7 a user-installed CA is
ignored by apps entirely, and Android 11 removed the install intent — so for a
managed fleet the policy route is not a convenience, it is the only route that works.

---

### 5d. Confirming it actually worked

Almost nobody finds out an install failed on the device they installed it on. They
find out on the fourth device, a week later, and they blame the phone.

The trust page ends with **4. Check it worked**, and nobody has to press anything:
it runs on load. It fetches a 1×1 image from the box over https, so a device that
trusts the box CA completes the handshake and one that does not, does not. Same signal
on every platform, nothing to install to use it.

It was a button first. A button is a thing to notice, and the person who most needs
this answer is the one who did not notice — so it now answers before it is asked, and
the button remains only as *Check again* for after you have fixed something.

Read the answer in one direction only:

- **Confirmed** is definitive. That device trusts this box.
- **Not confirmed** is *not* proof the CA is missing. A handshake also fails when the
  terminator is down or listening on another port. The message says so, and names the
  address it tried.

The check is only offered when it can give a true answer. If the box serves no HTTPS,
or the address this device used is not in the certificate, the page says *that*
instead — an unwinnable check reported as "not trusted" would send somebody to
reinstall a CA that was already fine.

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

## 7. Moving a box — a new room, a new country, new hardware

A box is a physical object and physical objects move. Exactly **one** thing on it
cannot be regenerated: the box CA's private key. The leaf certificate, the
Caddyfile, `ALLOWED_HOSTS`, the origins — all derived, all rebuilt in a minute.

Preserve the CA and a relocation is a reissue that no device notices. Lose it and
every phone, laptop and tablet that trusted this box must be physically revisited,
which for a school that has just moved is the difference between an afternoon and
a term.

```bash
# BEFORE the box is switched off. RMC_EDGE_TLS_CA_PASSPHRASE must be set in the
# environment -- it is deliberately not a command-line flag, because a command line
# is visible in `ps`, in shell history and in docker's own event log.
docker compose -f deploy/selfhost/docker-compose.yml exec \
  -e RMC_EDGE_TLS_CA_PASSPHRASE web \
  python manage.py edge_tls --export-ca /tmp/box-ca-bundle.p12

docker compose -f deploy/selfhost/docker-compose.yml \
  cp web:/tmp/box-ca-bundle.p12 ./box-ca-bundle.p12

# Write it to /tmp, NOT to the certificate directory. A backup that shares a volume
# with the key it protects survives none of the events a backup exists for, and
# check_edge_readiness reports a bundle left there as a finding.
#
# Store the copy somewhere that is NOT the box, and NOT beside the passphrase. It is
# encrypted PKCS#12 (AES-256) holding the CA PRIVATE KEY: whoever holds both can
# impersonate any site to every device that trusts this box.
```

Ask the box what a specific move requires. The steps genuinely differ by mode and
by what is changing, and a plan that lists every step for every move is a plan
people stop reading:

```bash
python manage.py edge_tls --plan-relocation --changed address
python manage.py edge_tls --plan-relocation --changed country,hardware
```

### Surviving an address change, which is the common case

Hardware replacement is rare. A changed IP is not: a new DHCP lease, a re-cabled
room, a different subnet at a new campus. A certificate names addresses, so any of
those invalidates it for the address people actually type. Three layers, and only
the first one is free.

**1. Do not depend on the IP.** If devices reach the box by a stable NAME, an
address change costs nothing at all — the certificate still asserts the name, and
only name resolution has to catch up. On a LAN with no DNS server, mDNS gives you
that for free: a `.local` name is answered by the box itself over multicast and
follows it to any address on the segment. No server, no records, nothing per
device — and `ALLOWED_HOSTS` already accepts `.local` by default.

Support is native on iOS, macOS, Windows 10+ and Android 12+. Where it is missing
(an old Android tablet, a kiosk browser), that device falls back to the IP, which
still works — mDNS is an addition, never a replacement.

**Two local conditions break `.local` specifically, and both are common enough to
check for first.** Neither produces an error that mentions mDNS:

- **The school's Windows domain is itself named `.local`.** Plenty are — it was the
  recommended layout for years. On a domain-joined machine the domain controller
  answers for everything under `.local`, so `gilead.local` resolves to nothing, or
  worse, to something else. Ask what the AD domain is called before choosing the
  name.
- **The access points filter multicast.** Client isolation, IGMP snooping without a
  querier, and "block peer-to-peer traffic" are all default-on in some school wifi
  controllers, and all of them drop the packets mDNS is carried in. Wired devices
  resolve the box, wireless ones do not, which reads as "it works in the office and
  not in the classrooms".

Where either holds, use a name in the school's own DNS instead and lean on the DHCP
reservation below. The certificate does not care which kind of name it is — only
that the name is stable.

**2. Pin the lease.** A DHCP reservation against the box's MAC address stops the
address moving within a site at all. Two minutes in the router, and it removes the
whole problem for a box that does not travel.

**3. Let the box heal itself when it changes anyway.**

```bash
python manage.py edge_tls --ensure
```

This runs on every boot already (`deploy/selfhost/entrypoint.web.sh`). It does
**nothing** unless the certificate is missing, no longer covers an address the box
answers at, or is inside its renewal window. When it does act it **reuses the CA on
disk**, so the repair is invisible to every device that installed it, and it
refuses to act on an impossible clock rather than minting a certificate that is
genuinely not-yet-valid.

Django must also *accept* the new address, or the box returns 400 to every request
— which is worse than a certificate warning, because nothing on screen explains it.
For a box that moves, or one on a network you do not control:

```bash
RMC_EDGE_TRUST_LOCAL_ADDRESSES=1
```

The box then serves, and asserts, the addresses it currently holds. Only its **own**
addresses, read from its routing table — never an arbitrary `Host` header — so the
protection `ALLOWED_HOSTS` exists to give is preserved: an attacker cannot make the
box hold an address it does not hold.

Together: a box can be unplugged, moved to another building, given a completely
different address by a different router, and come back working — with no device
touched and nobody editing a file.

### https://<ip>/ and why the site line is `:443`

Found on a live box, and it looks like nothing until you try it from a phone.

The box had a healthy terminator, a certificate that asserted `10.10.20.137`, and
`https://10.10.20.137/` **failed for every browser on the network** — not a warning
anyone could click through, a dead connection:

```
no SNI                -> "no peer certificate available"
SNI gilead-tech.local -> subject=CN=gilead-tech.local
SNI 10.10.20.137      -> subject=CN=gilead-tech.local
```

The TLS `server_name` extension carries DNS names only, and every browser omits it
for an IP literal. A **named** Caddy site block is a host matcher, and with no SNI
there is nothing to match — so Caddy presents no certificate at all. The leaf
asserted the IP the whole time; Caddy never got far enough to offer it.

This is worse than it sounds, in a specific way: a certificate a device does not
trust produces a warning with a *proceed anyway*. A handshake with no certificate in
it produces neither. So the box looks **more** broken to an untrained user than an
untrusted CA does, and every log it writes says healthy.

`edge_tls --print-caddyfile` therefore renders `:443` whenever the certificate
asserts any IP address, not only when the box is mobile, and adds the `:80` redirect
that a named block would have got automatically. It stays a named block where the
catch-all would not help: `acme` needs the named form for its own challenge and
cannot issue for a private IP anyway, and `tls internal` issues per SNI — which is
exactly what a no-SNI client cannot drive.

**This also explains `--check-terminator`.** It defaults to `edge-tls:443`, the
compose service name, which is never in the certificate. Against a named block that
reported `TLSV1_ALERT_INTERNAL_ERROR` about a terminator that was working; against
`:443` it gets the certificate and can compare it properly.

---

### The certificate healing is only half of it — the terminator has to be told

`--ensure` rewrites the certificate files. The TLS terminator read those files when
it loaded its configuration and does not re-read them per handshake, so until it is
restarted it goes on presenting the certificate for the address the box has left:

```bash
docker compose -f deploy/selfhost/docker-compose.yml --profile tls restart edge-tls
```

A whole-box reboot — a power cut, which in many places is the usual way a box
restarts — does this for free, because everything comes up together. It is a
`restart web` on its own that leaves the two halves disagreeing. `--ensure` prints
the command whenever it actually reissued.

The second half is subtler and worth understanding once. A Caddy site block that
begins `gilead.local, 10.10.20.137 {` is a **host matcher**: Caddy serves that block
only for a request whose `Host` is one of those. So a box that heals its certificate
onto a new address and keeps a pinned site line answers *nothing* at the new
address — and every log it writes says it is healthy. That is why a box declared
mobile renders `:443` instead, which matches any host and presents the pair this box
minted for all of them:

```bash
python manage.py edge_tls --print-caddyfile > deploy/selfhost/Caddyfile.edge
```

With `RMC_EDGE_TRUST_LOCAL_ADDRESSES=1` set, that is what you get automatically, and
the file then never needs regenerating for an address change again. It widens
nothing: `ALLOWED_HOSTS` is still the Host-header guard, and Caddy is the terminator,
not the gate.

### The name on the building, and how it reaches the certificate

A certificate carries DNS names as ASCII, so a box named in any other script — 学校,
مدرسة, écolé — is carried as its IDNA A-label: `écolé.local` becomes
`xn--col-9lad.local`. **This is correct and must not be "fixed".** It is what goes
on the wire for every internationalised domain name in the world, and browsers
convert it back, so the address bar still shows the name the school typed. The
readiness check says so explicitly when it sees one, because an operator who finds
`xn--` in a certificate reasonably assumes something is broken.

An address, meanwhile, is written two ways on purpose and each is wrong in the
other's place:

| Where | IPv6 is written | Why |
|---|---|---|
| `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, any URL | `[fd00::1]` | Django keeps the brackets when it parses the `Host` header; a bare entry matches nothing and every request is a bare 400 |
| `RMC_EDGE_TLS_HOSTNAMES`, the certificate | `fd00::1` | it goes in an `IPAddress` SAN entry, which holds an address, not text |

Both spellings are accepted wherever you type them and converted to the right one —
including `FD00::0001`, which is the same address as `fd00::1` and used to read as a
different one.

### On replacement hardware, restore before you issue

```bash
# 1. Restore the CA FIRST.
python manage.py edge_tls --import-ca /path/box-ca-bundle.p12

# 2. THEN issue a leaf for the new addresses. It chains to the restored CA, so the
#    devices that already trust it need nothing done to them.
python manage.py edge_tls --issue-selfsigned --force
```

Reversed, the box mints a *second* CA and every device is stranded. Restoring over
a different CA is refused unless you pass `--force`, so the mistake announces
itself instead of being discovered one device at a time.

### The parts of a move that are not the certificate

- **A new address must be in `ALLOWED_HOSTS` before the box answers at all.** Django
  rejects a host it was not told about, so a box at an unlisted new IP looks dead
  rather than misconfigured.
- **`CSRF_TRUSTED_ORIGINS` carries the scheme and the host.** A stale entry produces
  a login that submits, returns to the login page, and reports nothing.
- **A new country means a new `TIME_ZONE`.** Attendance, timetables, schedule
  due-ness and sync cursors are all evaluated locally on this box; left on the old
  zone they are silently wrong by the offset.
- **Check the clock.** A box whose RTC battery died in transit powers on believing it
  is years in the past and rejects its own certificate as "not yet valid" — a total
  TLS failure whose error message never mentions time. `check_edge_readiness`
  detects this without a network by comparing the clock to the box's own CA.
- **On `acme`, update the public DNS record as part of the move, not after it.**
  Renewal runs unattended about 30 days before expiry; if DNS still points at the
  old site it fails silently and the first symptom is a dead box weeks later.
  Consider DNS-01 for a box that moves, since it needs no inbound reachability.
- **Devices left at the old site still trust this box's CA.** If a *different* box
  takes over there, remove the old CA from them.

### A public CA cannot issue for a LAN address

This is the constraint that surprises schools, and it does not change by moving.
No public certificate authority will issue for `10.10.20.137` or `gilead.school.lan`
— nobody can demonstrate ownership of an address that resolves to a different
machine in every building on earth. An ACME order is also **all-or-nothing**: one
private name in the list means the box gets *no* certificate, not a partial one.

`check_edge_readiness` reports this as a blocking failure with the reason, rather
than letting the terminator retry an impossible order forever.

## 8. Reading the box's posture

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

## 9. What readiness will tell you

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

## 10. Related

- `apps/schools/edge_tls.py` — the policy, and why the database is deliberately not a
  layer in this particular cascade
- `deploy/selfhost/Caddyfile.edge`, `docker-compose.yml` (`--profile tls`)
- `docs/EDGE_LAN_HOSTNAME_DNS.md` — getting a name onto the LAN in the first place
- `docs/EDGE_UPDATE_PIPELINE.md` — how a new build reaches the box
- `docs/EDGE_TOPOLOGY.md`
